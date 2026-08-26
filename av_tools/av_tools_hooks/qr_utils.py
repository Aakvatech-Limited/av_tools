import base64
import io


def generate_approver_qr(content: str) -> str:
	"""Jinja method — registered in hooks.py under jinja.methods."""
	return _make_qr_base64(content)


def _make_qr_base64(content: str) -> str:
	import qrcode

	qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
	qr.add_data(content)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white")
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def get_qr_svg(data, size="70px"):
	"""Jinja method — returns an inline SVG QR code sized to fit a table cell."""
	import re

	import qrcode
	import qrcode.image.svg

	qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
	qr.add_data(str(data))
	qr.make(fit=True)
	img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
	buf = io.BytesIO()
	img.save(buf)
	svg = buf.getvalue().decode("utf-8")
	svg = re.sub(r'width="[^"]*"', f'width="{size}"', svg, count=1)
	svg = re.sub(r'height="[^"]*"', f'height="{size}"', svg, count=1)
	return svg
