# Django Quik

This project aims to provide extra power while developing Django applications such as livereload and tailwindcss support
while you modify template, static files .etc

It is a wrapper around Django CLI, and you don't need to modify your existing code or add it in installed apps
like other livereload packages.

## Installation

```bash
pip install django-quik
```

Make sure to install this package inside the same virtual environment if your project is using.
Now open url: [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Usage

The main motivation for Django Quik is to provide features without modifying your any code.

```bash
django-quik runserver
```

You can use all the Django commands with django quik.

## Setting up tailwindcss

Make sure you have installed npm in your system.

```bash
django-quik init tailwindcss
```

It will create two files: `tailwind.config.js` and `tailwind.mapping` after going through your
project `INSTALLED_APPS` and `TEMPLATES`.

MODIFY `tailwind.mapping` file based on your needs.

When you run `django-quik runserver`, it will run with tailwind livereload support.

## Does it support WebSocket?

Yes, Django Quik supports HTTP/1.0, HTTP/1.1, and WebSocket protocol. The HTTP/1.1 is overridden to HTTP/1.0.

## How Django Quik works?

Django Quik creates the proxy server then starts Django development server internally. It acts as the middleman between
the client and the Django server. If the content type is `text/html` being served, it injects script to reload page
which will be triggered from `Server Side Event(SSE)`.

## Conclusion

I am planning to add `tailwind` support soon.
Note: I have tested in Linux and it works.
