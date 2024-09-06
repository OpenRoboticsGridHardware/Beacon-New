import asyncio
import json
import websockets
from rpi_ws281x import PixelStrip, Color


LED_COUNT = 30  
LED_PIN = 18    
LED_BRIGHTNESS = 255  
LED_FREQ_HZ = 800000  
LED_DMA = 10    
LED_INVERT = False  

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
strip.begin()

def set_color(r, g, b):
    """Set the color of all addressable LEDs.

    Args:
        r (int): Red value (0-255)
        g (int): Green value (0-255)
        b (int): Blue value (0-255)
    """
    color = Color(r, g, b)
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
    strip.show()

def turn_off_leds():
    """Turn off all addressable LEDs."""
    set_color(0, 0, 0)

def validate_color_data(data):
    """Validate that the JSON data contains the correct keys and values.

    Args:
        data (dict): The parsed JSON data.

    Returns:
        tuple: (bool, str) where the first value indicates if the data is valid,
               and the second is an error message or an empty string.
    """
    required_keys = {"red", "green", "blue"}

    # Check if all required keys are present
    if not required_keys.issubset(data.keys()):
        missing = required_keys - data.keys()
        return False, f"Missing keys: {', '.join(missing)}"

    # Check for any extra keys
    allowed_keys = required_keys | {"duration"}  # Allow duration as an optional key
    if not data.keys() <= allowed_keys:
        extra_keys = data.keys() - allowed_keys
        return False, f"Extra keys present: {', '.join(extra_keys)}"

    # Check if all values are within the acceptable range (0-255)
    for key in required_keys:
        value = data.get(key)
        if not isinstance(value, int) or not (0 <= value <= 255):
            return False, f"Invalid value for {key}: {value} (must be an integer between 0 and 255)"

    # Validate the optional duration value if it exists
    if "duration" in data:
        duration = data["duration"]
        if not isinstance(duration, (int, float)) or duration <= 0:
            return False, f"Invalid duration value: {duration} (must be a positive number)"

    return True, ""

async def handler(websocket, path):
    async for message in websocket:
        try:
            # Parse the JSON message
            data = json.loads(message)

            # Validate the JSON data
            is_valid, error_message = validate_color_data(data)
            if not is_valid:
                print(error_message)
                response = json.dumps({"status": "Error", "message": error_message})
                await websocket.send(response)
                continue

            r = data["red"]
            g = data["green"]
            b = data["blue"]
            duration = data.get("duration", None)  # Get duration if provided, otherwise None

            # Set the color of the LEDs
            set_color(r, g, b)

            # Send an acknowledgment back to the client
            response = json.dumps({"status": "OK"})
            await websocket.send(response)

            # If duration is specified, wait for the duration and then turn off the LEDs
            if duration:
                await asyncio.sleep(duration)
                turn_off_leds()

        except json.JSONDecodeError:
            print("Failed to decode JSON")
            response = json.dumps({"status": "Error", "message": "Invalid JSON format"})
            await websocket.send(response)
        except Exception as e:
            print(f"An error occurred: {e}")
            response = json.dumps({"status": "Error", "message": str(e)})
            await websocket.send(response)

start_server = websockets.serve(handler, "0.0.0.0", 8765)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except KeyboardInterrupt:
    pass
finally:
    # Cleanup code if needed (in this case, we don't need extra cleanup for the strip)
    pass
