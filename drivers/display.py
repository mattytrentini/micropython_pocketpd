"""SSD1306 OLED display wrapper with text rendering via nano-gui Writer.

Provides a high-level interface for rendering text at different sizes
on the 128x64 monochrome OLED used by PocketPD.
"""

import framebuf

import fonts.large as large_font
import fonts.medium as medium_font
import fonts.small as small_font
from lib.nano_gui.writer import Writer

# Display dimensions
WIDTH = 128
HEIGHT = 64


class Display:
    """SSD1306 display wrapper with multi-font text rendering.

    Wraps a framebuf.FrameBuffer-based display (like SSD1306_I2C) and provides
    Writer instances for three font sizes.
    """

    def __init__(self, device):
        """Initialize display with a FrameBuffer-based device.

        Args:
            device: SSD1306_I2C instance or any FrameBuffer with .show(), .width, .height
        """
        self.device = device
        self.width = device.width
        self.height = device.height

        self.wri_large = Writer(device, large_font, verbose=False)
        self.wri_medium = Writer(device, medium_font, verbose=False)
        self.wri_small = Writer(device, small_font, verbose=False)

        # Disable clipping — we manage layout manually
        self.wri_large.set_clip(True, True, False)
        self.wri_medium.set_clip(True, True, False)
        self.wri_small.set_clip(True, True, False)

    def clear(self):
        """Clear the display buffer."""
        self.device.fill(0)

    def show(self):
        """Push the buffer to the physical display."""
        self.device.show()

    def text_large(self, text, row, col):
        """Render text in large font (~35px) at the given position."""
        Writer.set_textpos(self.device, row, col)
        self.wri_large.printstring(text)

    def text_medium(self, text, row, col):
        """Render text in medium font (~20px) at the given position."""
        Writer.set_textpos(self.device, row, col)
        self.wri_medium.printstring(text)

    def text_small(self, text, row, col):
        """Render text in small font (~10px) at the given position."""
        Writer.set_textpos(self.device, row, col)
        self.wri_small.printstring(text)

    def hline(self, x, y, w, color=1):
        """Draw a horizontal line."""
        self.device.hline(x, y, w, color)

    def vline(self, x, y, h, color=1):
        """Draw a vertical line."""
        self.device.vline(x, y, h, color)

    def rect(self, x, y, w, h, color=1):
        """Draw a rectangle outline."""
        self.device.rect(x, y, w, h, color)

    def fill_rect(self, x, y, w, h, color=1):
        """Draw a filled rectangle."""
        self.device.fill_rect(x, y, w, h, color)

    def pixel(self, x, y, color=1):
        """Set a single pixel."""
        self.device.pixel(x, y, color)
