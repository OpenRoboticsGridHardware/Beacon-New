import asyncio
import RPi.GPIO as GPIO
import websockets
import json

LED1_PINS = {'red': 17, 'green': 27, 'blue': 22}
LED2_PINS = {'red': 23, 'green': 24, 'blue': 25}
LED3_PINS = {'red': 5, 'green': 6, 'blue': 16}
GPIO.setmode(GPIO.BCM)
leds = []
for pins in [LED1_PINS, LED2_PINS, LED3_PINS]:
    GPIO.setup(pins['red'], GPIO.OUT)
    GPIO.setup(pins['green'], GPIO.OUT)
    GPIO.setup(pins['blue'], GPIO.OUT)

    leds.append({
        'red': GPIO.PWM(pins['red'], 1000),  
        'green': GPIO.PWM(pins['green'], 1000),
        'blue': GPIO.PWM(pins['blue'], 1000)
    })

for led in leds:
    led['red'].start(0)
    led['green'].start(0)
    led['blue'].start(0)

def set_color(r, g, b):
    """Set the color of all RGB LEDs.
    
    Args:
        r (int): Red value (0-255)
        g (int): Green value (0-255)
        b (int): Blue value (0-255)
    """
    for led in leds:
        led['red'].ChangeDutyCycle(r / 255 * 100)
        led['green'].ChangeDutyCycle(g / 255 * 100)
        led['blue'].ChangeDutyCycle(b / 255 * 100)

def turn_off_leds():
    """Turn off all RGB LEDs."""
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
    for led in leds:
        led['red'].stop()
        led['green'].stop()
        led['blue'].stop()
    GPIO.cleanup()
