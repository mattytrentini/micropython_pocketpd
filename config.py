"""PocketPD hardware configuration — pin assignments, I2C addresses, timing constants."""

# I2C bus (shared by AP33772, INA226, SSD1306)
I2C_ID = 0
I2C_SDA = 4
I2C_SCL = 5
I2C_FREQ = 400_000  # 400kHz — SSD1306 framebuffer write times out at 100kHz

# I2C device addresses
ADDR_AP33772 = 0x51
ADDR_INA226 = 0x40
ADDR_SSD1306 = 0x3C

# Output control
PIN_OUTPUT_EN = 1  # Active high — enables power output

# Buttons (active low, pull-up)
PIN_BTN_OUTPUT = 10  # Toggle output on/off
PIN_BTN_SELECT = 11  # Toggle voltage/current adjustment

# Rotary encoder
PIN_ENC_SW = 18  # Encoder push button (active low, pull-up)
PIN_ENC_CLK = 19  # Encoder A
PIN_ENC_DATA = 20  # Encoder B

# INA226 calibration (HW1.1+ production units)
SHUNT_RESISTANCE = 0.005  # 5mΩ
MAX_EXPECTED_CURRENT = 5.5  # Amps

# Timing (milliseconds)
SENSOR_LOOP_MS = 33  # ~30 Hz sensor/display refresh
BLINK_LOOP_MS = 500  # Cursor blink animation
SAVE_LOOP_MS = 2000  # Settings save interval

# Button timing (milliseconds)
DEBOUNCE_MS = 50
SHORT_PRESS_MAX_MS = 1000
LONG_PRESS_MIN_MS = 1500
