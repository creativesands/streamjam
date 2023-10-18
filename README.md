# StreamJam 🎵

Unifying frontend and backend into one Pythonic experience for sleek, interactive web apps.

## Overview

StreamJam allows developers to craft both the frontend and backend of web applications using just Python. Inspired by the reactivity of Svelte and the real-time capabilities of Phoenix LiveView, StreamJam offers a streamlined approach to web development.

## Features

- **Reactive Components**: Write dynamic, interactive components using Python.
- **Unified Development**: No need to juggle between frontend and backend languages. Everything's in Python!
- **Elegant Syntax**: Inspired by modern frameworks like Svelte, StreamJam keeps your codebase clean and concise.

## Installation

```bash
pip install streamjam
```

## Example: Countdown Timer

Here's a simple countdown timer using StreamJam:

**Filename**: `Timer.pie`

```python
from streamjam import pie

template = """
<div class="countdown-timer">
    <h1>{title}</h1>
    <p>Time left: {time_left} seconds</p>
    <button onclick={start}>Start</button>
    <button onclick={stop}>Stop</button>
</div>
"""

class Component:
    title: pie[str] = "New Timer"
    time_left: pie[int] = 10
    interval = None  # not a pie

    def start(self):
        self.interval = setInterval(self.tick, 1000)

    def tick(self):
        if self.time_left > 0:
            self.time_left -= 1  # changes will be sent to the client
        else:
            self.stop()

    def stop(self):
        clearInterval(self.interval)
        self.interval = None

style = """
.countdown-timer {
    font-family: Arial, sans-serif;
    text-align: center;
    background-color: #f5f5f5;
    padding: 20px;
    border-radius: 8px;
}
"""

```

## Documentation

Visit our [official documentation](#) for detailed guides, API references, and more.

## Contributing

Contributions are always welcome! Please see our [contributing guidelines](#) for more details.

## License

[MIT License](LICENSE)