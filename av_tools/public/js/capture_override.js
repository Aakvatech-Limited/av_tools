(function () {
	var captureSettingsRequest;

	function getCaptureSettings() {
		if (!captureSettingsRequest) {
			captureSettingsRequest = frappe
				.call("av_tools.av_tools_hooks.capture.get_capture_settings")
				.then(function (response) {
					return response.message;
				})
				.catch(function () {
					return { enabled: false };
				});
		}

		return captureSettingsRequest;
	}

	function renderStream(capture, settings) {
		var constraints = {
			video: {
				facingMode: { ideal: capture.facing_mode },
				width: { ideal: settings.ideal_width },
				height: { ideal: settings.ideal_height },
			},
			audio: false,
		};

		return navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
			capture.stream = stream;
			capture.dialog.custom_actions.empty();
			capture.dialog.get_primary_btn().off("click");
			capture.setup_take_photo_action();
			capture.setup_preview_action();
			capture.setup_toggle_camera();
			capture.$template.find(".fc-stream-container").show();
			capture.$template.find(".fc-preview-container").hide();
			capture.video = capture.$template.find("video")[0];
			capture.video.srcObject = stream;
			capture.video.load();

			return capture.video.play();
		});
	}

	function installCaptureOverride() {
		if (
			!frappe.ui ||
			!frappe.ui.Capture ||
			frappe.ui.Capture.__av_tools_capture_override_installed
		) {
			return;
		}

		var originalRenderStream = frappe.ui.Capture.prototype.render_stream;

		frappe.ui.Capture.prototype.render_stream = function () {
			var capture = this;

			return getCaptureSettings().then(function (settings) {
				if (!settings.enabled) {
					return originalRenderStream.call(capture);
				}

				return renderStream(capture, settings);
			});
		};

		frappe.ui.Capture.__av_tools_capture_override_installed = true;
	}

	$(installCaptureOverride);
})();
