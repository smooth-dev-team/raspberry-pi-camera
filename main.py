#!/usr/bin/env python3
"""
SmoothBox Raspberry Pi Camera
Captures images and sends to NVIDIA Jetson Orin based on ToF sensor triggers

Responsibilities:
1. Read VL53L1X Time-of-Flight sensor
2. Detect vehicle presence/absence based on distance
3. Capture images from Pi Camera
4. Send images + spot_number to NVIDIA Orin
5. Implement event-based triggering (entry, exit, verification)
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import yaml

try:
    from picamera2 import Picamera2, Preview
    import numpy as np
except ImportError:
    print("Warning: picamera2 not available. Running in simulation mode.")
    Picamera2 = None

try:
    import VL53L1X
except ImportError:
    print("Warning: VL53L1X library not available. Running without ToF sensor.")
    VL53L1X = None

import aiohttp
import io
from PIL import Image


class ToFSensor:
    """VL53L1X Time-of-Flight Distance Sensor Handler"""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("ToFSensor")
        self.enabled = config.get("enabled", True) and VL53L1X is not None
        self.sensor = None
        self.current_distance = None
        self.distance_history = []

        if not self.enabled:
            self.logger.warning("ToF sensor disabled or library not available")

    def initialize(self):
        """Initialize the ToF sensor"""
        if not self.enabled:
            return

        try:
            # Initialize VL53L1X sensor
            self.sensor = VL53L1X.VL53L1X(i2c_bus=self.config["i2c_bus"], i2c_address=self.config["i2c_address"])
            self.sensor.open()
            self.sensor.start_ranging(1)  # 1 = short distance mode
            self.logger.info(f"ToF sensor initialized on I2C bus {self.config['i2c_bus']}")
        except Exception as e:
            self.logger.error(f"Failed to initialize ToF sensor: {e}")
            self.enabled = False

    def read_distance(self) -> Optional[int]:
        """
        Read current distance from sensor

        Returns:
            Distance in millimeters, or None if sensor failed
        """
        if not self.enabled:
            return None

        try:
            distance = self.sensor.get_distance()
            self.current_distance = distance

            # Update smoothing history
            smoothing_window = self.config["sampling"]["smoothing_window"]
            self.distance_history.append(distance)
            if len(self.distance_history) > smoothing_window:
                self.distance_history.pop(0)

            return distance

        except Exception as e:
            self.logger.error(f"Failed to read ToF sensor: {e}")
            return None

    def get_smoothed_distance(self) -> Optional[int]:
        """Get moving average of distance readings"""
        if not self.distance_history:
            return self.current_distance

        return int(sum(self.distance_history) / len(self.distance_history))

    def is_vehicle_present(self) -> bool:
        """Check if vehicle is currently present based on distance"""
        distance = self.get_smoothed_distance()
        if distance is None:
            return False

        threshold = self.config["thresholds"]["vehicle_present_mm"]
        return distance < threshold

    def is_vehicle_absent(self) -> bool:
        """Check if vehicle is absent based on distance"""
        distance = self.get_smoothed_distance()
        if distance is None:
            return True  # Assume absent if sensor fails

        threshold = self.config["thresholds"]["vehicle_absent_mm"]
        return distance > threshold

    def close(self):
        """Close the sensor connection"""
        if self.sensor:
            try:
                self.sensor.stop_ranging()
                self.sensor.close()
            except Exception as e:
                self.logger.error(f"Error closing ToF sensor: {e}")


class CameraHandler:
    """Raspberry Pi Camera Handler"""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("CameraHandler")
        self.camera = None
        self.enabled = Picamera2 is not None

        if not self.enabled:
            self.logger.warning("picamera2 not available. Running in simulation mode.")

    def initialize(self):
        """Initialize the Raspberry Pi camera"""
        if not self.enabled:
            return

        try:
            self.camera = Picamera2()

            # Configure camera
            camera_config = self.camera.create_still_configuration(
                main={
                    "size": (
                        self.config["resolution"]["width"],
                        self.config["resolution"]["height"]
                    ),
                    "format": "RGB888"
                }
            )
            self.camera.configure(camera_config)

            # Set camera parameters
            if self.config.get("rotation"):
                self.camera.set_controls({"Rotation": self.config["rotation"]})

            if self.config.get("brightness"):
                self.camera.set_controls({"Brightness": self.config["brightness"] / 100.0})

            self.camera.start()
            self.logger.info("Raspberry Pi camera initialized")

        except Exception as e:
            self.logger.error(f"Failed to initialize camera: {e}")
            self.enabled = False

    def capture_image(self) -> Optional[bytes]:
        """
        Capture image from camera

        Returns:
            JPEG image as bytes, or None if capture failed
        """
        if not self.enabled:
            # Simulation mode: return dummy image
            return self._create_dummy_image()

        try:
            # Capture image
            image_array = self.camera.capture_array()

            # Convert to PIL Image
            pil_image = Image.fromarray(image_array)

            # Encode as JPEG
            buffer = io.BytesIO()
            pil_image.save(
                buffer,
                format=self.config["format"].upper(),
                quality=self.config["quality"]
            )
            buffer.seek(0)

            return buffer.getvalue()

        except Exception as e:
            self.logger.error(f"Failed to capture image: {e}")
            return None

    def _create_dummy_image(self) -> bytes:
        """Create a dummy image for testing"""
        image = Image.new('RGB', (640, 480), color='blue')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        buffer.seek(0)
        return buffer.getvalue()

    def close(self):
        """Close the camera"""
        if self.camera:
            try:
                self.camera.stop()
                self.camera.close()
            except Exception as e:
                self.logger.error(f"Error closing camera: {e}")


class NVIDIAClient:
    """Client for sending images to NVIDIA Jetson Orin"""

    def __init__(self, config: dict, station_id: str, spot_number: int):
        self.config = config
        self.station_id = station_id
        self.spot_number = spot_number
        self.logger = logging.getLogger("NVIDIAClient")

        # Build endpoint URL
        protocol = config.get("protocol", "http")
        ip = config["ip_address"]
        port = config["port"]
        endpoint = config.get("endpoint", "/receive_image")
        self.url = f"{protocol}://{ip}:{port}{endpoint}"

        self.logger.info(f"NVIDIA client configured: {self.url}")

    async def send_image(self, image_data: bytes) -> bool:
        """
        Send image to NVIDIA Jetson Orin

        Args:
            image_data: JPEG image as bytes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare multipart form data
            data = aiohttp.FormData()
            data.add_field('image',
                          image_data,
                          filename='capture.jpg',
                          content_type='image/jpeg')
            data.add_field('station_id', self.station_id)
            data.add_field('spot_number', str(self.spot_number))
            data.add_field('timestamp', datetime.now().isoformat())

            # Send request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, data=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        self.logger.debug(f"Image sent successfully (spot #{self.spot_number})")
                        return True
                    else:
                        self.logger.warning(f"Image send failed: HTTP {response.status}")
                        return False

        except asyncio.TimeoutError:
            self.logger.error("Image send timeout")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send image: {e}")
            return False


class SmoothBoxCamera:
    """Main application for Raspberry Pi camera system"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.running = False

        # Initialize components
        self.tof_sensor = ToFSensor(self.config["tof_sensor"])
        self.camera = CameraHandler(self.config["camera"])
        self.nvidia_client = NVIDIAClient(
            self.config["nvidia"],
            self.config["device"]["station_id"],
            self.config["device"]["spot_number"]
        )

        # State management
        self.vehicle_present = False
        self.last_entry_time = None
        self.last_exit_time = None
        self.last_verification_time = None

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_config = self.config["logging"]
        log_file = Path(log_config["file"])
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, log_config["level"]),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout),
            ],
        )

        logger = logging.getLogger("SmoothBoxCamera")
        logger.info(
            f"Camera initialized - Station: {self.config['device']['station_id']} | "
            f"Spot: {self.config['device']['spot_number']}"
        )
        return logger

    async def start(self):
        """Start the camera system"""
        self.logger.info("Starting SmoothBox Camera System")

        # Initialize hardware
        self.tof_sensor.initialize()
        self.camera.initialize()

        self.running = True

        # Start background tasks
        tasks = [
            asyncio.create_task(self._tof_monitoring_loop()),
            asyncio.create_task(self._periodic_verification_loop()),
        ]

        # Add fallback task if ToF is disabled
        if not self.tof_sensor.enabled:
            tasks.append(asyncio.create_task(self._fallback_capture_loop()))

        self.logger.info("All systems operational")

        # Wait for tasks
        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop the camera system"""
        self.logger.info("Stopping SmoothBox Camera System")
        self.running = False

        # Close hardware
        self.tof_sensor.close()
        self.camera.close()

        self.logger.info("System stopped")

    async def _tof_monitoring_loop(self):
        """Monitor ToF sensor and trigger image captures"""
        if not self.tof_sensor.enabled:
            self.logger.info("ToF monitoring disabled")
            return

        sample_interval = 1.0 / self.config["tof_sensor"]["sampling"]["frequency_hz"]

        while self.running:
            try:
                # Read sensor
                distance = self.tof_sensor.read_distance()

                if distance is None:
                    await asyncio.sleep(sample_interval)
                    continue

                # Check for state changes
                is_present = self.tof_sensor.is_vehicle_present()
                is_absent = self.tof_sensor.is_vehicle_absent()

                # Entry event: vehicle just arrived
                if is_present and not self.vehicle_present:
                    self.logger.info(f"Vehicle entry detected (distance: {distance}mm)")
                    self.vehicle_present = True
                    self.last_entry_time = datetime.now()

                    # Trigger entry image capture
                    if self.config["tof_sensor"]["triggers"]["entry_event"]["enabled"]:
                        asyncio.create_task(self._capture_entry_sequence())

                # Exit event: vehicle just left
                elif is_absent and self.vehicle_present:
                    self.logger.info(f"Vehicle exit detected (distance: {distance}mm)")
                    self.vehicle_present = False
                    self.last_exit_time = datetime.now()

                    # Trigger exit image capture
                    if self.config["tof_sensor"]["triggers"]["exit_event"]["enabled"]:
                        if self.config["tof_sensor"]["triggers"]["exit_event"]["send_immediate"]:
                            asyncio.create_task(self._capture_single_image("exit"))

                await asyncio.sleep(sample_interval)

            except Exception as e:
                self.logger.error(f"Error in ToF monitoring: {e}")
                await asyncio.sleep(1)

    async def _capture_entry_sequence(self):
        """Capture sequence of images during vehicle entry"""
        config = self.config["tof_sensor"]["triggers"]["entry_event"]
        duration = config["send_duration_seconds"]
        interval = config["send_interval_seconds"]

        self.logger.info(f"Starting entry capture sequence: {duration}s @ {interval}s intervals")

        end_time = datetime.now() + timedelta(seconds=duration)

        while datetime.now() < end_time and self.running:
            await self._capture_single_image("entry")
            await asyncio.sleep(interval)

        self.logger.info("Entry capture sequence complete")

    async def _capture_single_image(self, event_type: str = "capture"):
        """Capture and send a single image to NVIDIA"""
        try:
            # Capture image
            image_data = self.camera.capture_image()

            if image_data is None:
                self.logger.warning("Failed to capture image")
                return

            # Send to NVIDIA
            success = await self.nvidia_client.send_image(image_data)

            if success:
                self.logger.debug(f"{event_type.capitalize()} image sent")
            else:
                self.logger.warning(f"Failed to send {event_type} image")

        except Exception as e:
            self.logger.error(f"Error capturing image: {e}")

    async def _periodic_verification_loop(self):
        """Periodic verification while vehicle is parked"""
        if not self.config["tof_sensor"]["triggers"]["periodic_check"]["enabled"]:
            self.logger.info("Periodic verification disabled")
            return

        interval = self.config["tof_sensor"]["triggers"]["periodic_check"]["interval_seconds"]
        duration = self.config["tof_sensor"]["triggers"]["periodic_check"]["send_duration_seconds"]
        send_interval = self.config["tof_sensor"]["triggers"]["periodic_check"]["send_interval_seconds"]

        while self.running:
            await asyncio.sleep(interval)

            if not self.vehicle_present:
                continue

            self.logger.info("Starting periodic verification check")
            self.last_verification_time = datetime.now()

            # Send images for verification duration
            end_time = datetime.now() + timedelta(seconds=duration)
            while datetime.now() < end_time and self.running and self.vehicle_present:
                await self._capture_single_image("verification")
                await asyncio.sleep(send_interval)

            self.logger.info("Verification check complete")

    async def _fallback_capture_loop(self):
        """Fallback periodic capture when ToF sensor is disabled"""
        if not self.config["fallback"]["periodic_capture"]["enabled"]:
            return

        interval = self.config["fallback"]["periodic_capture"]["interval_seconds"]
        self.logger.info(f"Fallback periodic capture enabled: every {interval}s")

        while self.running:
            await asyncio.sleep(interval)
            await self._capture_single_image("fallback")

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop())


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="SmoothBox Raspberry Pi Camera")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file",
    )
    args = parser.parse_args()

    # Create and start system
    system = SmoothBoxCamera(args.config)

    # Setup signal handlers
    signal.signal(signal.SIGINT, system.handle_shutdown)
    signal.signal(signal.SIGTERM, system.handle_shutdown)

    # Start system
    await system.start()


if __name__ == "__main__":
    asyncio.run(main())
