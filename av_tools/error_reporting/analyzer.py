import os
import re

import frappe

FRAME_RE = re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+), in (?P<function>.+)$')


def analyze_error_log(error_log):
	traceback_text = error_log.error or ""
	frames = []
	for line in traceback_text.splitlines():
		match = FRAME_RE.match(line)
		if not match:
			continue
		frame = match.groupdict()
		frame["line"] = int(frame["line"])
		frames.append(frame)

	frame = _select_actionable_frame(frames)
	exception_type, exception_message = _parse_exception(traceback_text)
	if not frame:
		return None

	app_name, relative_path = _app_from_path(frame["path"])
	if not app_name:
		return None

	module_name, component_type, component_name = _classify(relative_path)
	return {
		"app_name": app_name,
		"module_name": module_name,
		"component_type": component_type,
		"component_name": component_name,
		"file_path": relative_path,
		"function_name": frame["function"],
		"line_number": frame["line"],
		"exception_type": exception_type or "UnknownError",
		"exception_message": exception_message,
		"representative_traceback": traceback_text,
		"source_context": _source_context(frame["path"], frame["line"]),
		"latest_local_error_log": error_log.name,
	}


def _select_actionable_frame(frames):
	app_frames = [frame for frame in frames if "/apps/" in frame["path"] or frame["path"].startswith("apps/")]
	return app_frames[-1] if app_frames else None


def _app_from_path(path):
	normalized = path.replace("\\", "/")
	marker = "/apps/"
	if marker in normalized:
		tail = normalized.split(marker, 1)[1]
	elif normalized.startswith("apps/"):
		tail = normalized[5:]
	else:
		return None, None
	parts = tail.split("/")
	if len(parts) < 2:
		return None, None
	app_name = parts[0]
	relative_path = "/".join(parts[1:])
	return app_name, relative_path


def _classify(relative_path):
	parts = relative_path.split("/")
	lowered = [part.lower() for part in parts]
	module_name = parts[1].replace("_", " ").title() if len(parts) > 2 else None
	component_type = "Unknown"
	component_name = None
	for marker, kind in (
		("doctype", "DocType"),
		("report", "Report"),
		("page", "Page"),
		("patches", "Patch"),
		("api", "API"),
		("utils", "Utility"),
	):
		if marker in lowered:
			index = lowered.index(marker)
			component_type = kind
			if index + 1 < len(parts):
				component_name = parts[index + 1].replace("_", " ").title()
			break
	return module_name, component_type, component_name


def _parse_exception(traceback_text):
	for line in reversed(traceback_text.splitlines()):
		stripped = line.strip()
		if not stripped or stripped.startswith("Traceback") or stripped.startswith("File "):
			continue
		if ":" in stripped:
			exc, message = stripped.split(":", 1)
			if exc and " " not in exc:
				return exc.strip(), message.strip()
		if stripped.endswith(("Error", "Exception")):
			return stripped, ""
	return None, None


def _source_context(path, line_number, radius=5):
	normalized = path
	if not os.path.isabs(normalized):
		normalized = os.path.join(frappe.utils.get_bench_path(), normalized)
	try:
		with open(normalized, encoding="utf-8") as handle:
			lines = handle.readlines()
	except Exception:
		return None
	start = max(1, line_number - radius)
	end = min(len(lines), line_number + radius)
	output = []
	for index in range(start, end + 1):
		marker = ">>" if index == line_number else "  "
		output.append(f"{marker} {index}: {lines[index - 1].rstrip()}")
	return "\n".join(output)
