"""
Command line layout definitions
-------------------------------

The layout of a command line interface is defined by a Container instance.
There are two main groups of classes here. Containers and controls:

- A container can contain other containers or controls, it can have multiple
  children and it decides about the dimensions.
- A control is responsible for rendering the actual content to a screen.
  A control can propose some dimensions, but it's the container who decides
  about the dimensions -- or when the control consumes more space -- which part
  of the control will be visible.


Container classes::

    - Container (Abstract base class)
       |- HSplit (Horizontal split)
       |- VSplit (Vertical split)
       |- FloatContainer (Container which can also contain menus and other floats)
       `- Window (Container which contains one actual control

Control classes::

    - UIControl (Abstract base class)
       |- FormattedTextControl (Renders formatted text, or a simple list of text fragments)
       `- BufferControl (Renders an input buffer.)


Usually, you end up wrapping every control inside a `Window` object, because
that's the only way to render it in a layout.

There are some prepared toolbars which are ready to use::

- SystemToolbar (Shows the 'system' input buffer, for entering system commands.)
- ArgToolbar (Shows the input 'arg', for repetition of input commands.)
- SearchToolbar (Shows the 'search' input buffer, for incremental search.)
- CompletionsToolbar (Shows the completions of the current buffer.)
- ValidationToolbar (Shows validation errors of the current buffer.)

And one prepared menu:

- CompletionsMenu

"""

from __future__ import annotations

from .containers import (
    AnyContainer,
    ColorColumn,
    ConditionalContainer,
    Container,
    DynamicContainer,
    Float,
    FloatContainer,
    HorizontalAlign,
    HSplit,
    ScrollOffsets,
    VerticalAlign,
    VSplit,
    Window,
    WindowAlign,
    WindowRenderInfo,
    is_container,
    to_container,
    to_window,
)
from .controls import (
    BufferControl,
    DummyControl,
    FormattedTextControl,
    SearchBufferControl,
    UIContent,
    UIControl,
)
from .dimension import (
    AnyDimension,
    D,
    Dimension,
    is_dimension,
    max_layout_dimensions,
    sum_layout_dimensions,
    to_dimension,
)
from .layout import InvalidLayoutError, Layout, walk
from .margins import (
    ConditionalMargin,
    Margin,
    NumberedMargin,
    PromptMargin,
    ScrollbarMargin,
)
from .menus import CompletionsMenu, MultiColumnCompletionsMenu
from .scrollable_pane import ScrollablePane

__all__ = [
    # Layout.
    "Layout",
    "InvalidLayoutError",
    "walk",
    # Dimensions.
    "AnyDimension",
    "Dimension",
    "D",
    "sum_layout_dimensions",
    "max_layout_dimensions",
    "to_dimension",
    "is_dimension",
    # Containers.
    "AnyContainer",
    "Container",
    "HorizontalAlign",
    "VerticalAlign",
    "HSplit",
    "VSplit",
    "FloatContainer",
    "Float",
    "WindowAlign",
    "Window",
    "WindowRenderInfo",
    "ConditionalContainer",
    "ScrollOffsets",
    "ColorColumn",
    "to_container",
    "to_window",
    "is_container",
    "DynamicContainer",
    "ScrollablePane",
    # Controls.
    "BufferControl",
    "SearchBufferControl",
    "DummyControl",
    "FormattedTextControl",
    "UIControl",
    "UIContent",
    # Margins.
    "Margin",
    "NumberedMargin",
    "ScrollbarMargin",
    "ConditionalMargin",
    "PromptMargin",
    # Menus.
    "CompletionsMenu",
    "MultiColumnCompletionsMenu",
]
