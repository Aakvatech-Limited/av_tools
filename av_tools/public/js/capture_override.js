(function () {
	var defaultCaptureSettings = {
		enabled: 0,
		ideal_width: 1920,
		ideal_height: 1080,
		min_width: 0,
		min_height: 0,
	};
	var captureSettings = null;
	var captureSettingsRequest = null;

	function parsePositiveInt(value, fallback) {
		var parsed = parseInt(value, 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
	}

	function normalizeCaptureSettings(settings) {
		return {
			enabled: Boolean(Number(settings && settings.enabled)),
			ideal_width: parsePositiveInt(
				settings && settings.ideal_width,
				defaultCaptureSettings.ideal_width
			),
			ideal_height: parsePositiveInt(
				settings && settings.ideal_height,
				defaultCaptureSettings.ideal_height
			),
			min_width: parsePositiveInt(
				settings && settings.min_width,
				defaultCaptureSettings.min_width
			),
			min_height: parsePositiveInt(
				settings && settings.min_height,
				defaultCaptureSettings.min_height
			),
		};
	}

	function loadCaptureSettings() {
		if (captureSettings) {
			return Promise.resolve(captureSettings);
		}

		if (captureSettingsRequest) {
			return captureSettingsRequest;
		}

		captureSettingsRequest = new Promise(function (resolve) {
			frappe.call({
				method: "av_tools.av_tools_hooks.capture.get_capture_settings",
				callback: function (response) {
					captureSettings = normalizeCaptureSettings(
						response.message || defaultCaptureSettings
					);
					resolve(captureSettings);
				},
				error: function () {
					captureSettings = normalizeCaptureSettings(defaultCaptureSettings);
					resolve(captureSettings);
				},
			});
		}).finally(function () {
			captureSettingsRequest = null;
		});

		return captureSettingsRequest;
	}

	function buildConstraints(capture, settings) {
		var video = {
			facingMode: {
				ideal: capture.facing_mode,
			},
		};

		if (settings.min_width || settings.ideal_width) {
			video.width = {};
			if (settings.min_width) {
				video.width.min = settings.min_width;
			}
			if (settings.ideal_width) {
				video.width.ideal = settings.ideal_width;
			}
		}

		if (settings.min_height || settings.ideal_height) {
			video.height = {};
			if (settings.min_height) {
				video.height.min = settings.min_height;
			}
			if (settings.ideal_height) {
				video.height.ideal = settings.ideal_height;
			}
		}

		return {
			video: video,
			audio: false,
		};
	}

	function renderStreamWithConstraints(capture, constraints) {
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
			capture.video.srcObject = capture.stream;
			capture.video.load();

			var playPromise = capture.video.play();
			if (playPromise && typeof playPromise.then === "function") {
				return playPromise;
			}

			return undefined;
		});
	}

	function installCaptureOverride() {
		if (
			!frappe.ui ||
			!frappe.ui.Capture ||
			frappe.ui.Capture.__av_tools_capture_override_installed
		) {
			return Boolean(frappe.ui && frappe.ui.Capture);
		}

		var proto = frappe.ui.Capture.prototype;
		var originalShow = proto.show;
		var originalRenderStream = proto.render_stream;

		proto.show = function () {
			if (!frappe.is_mobile()) {
				return originalShow.call(this);
			}

			if (!captureSettings) {
				loadCaptureSettings();
				return originalShow.call(this);
			}

			if (!captureSettings.enabled) {
				return originalShow.call(this);
			}

			this.build_dialog();
			return this.show_for_desktop();
		};

		proto.render_stream = function () {
			var me = this;

			return loadCaptureSettings().then(function (settings) {
				if (!settings.enabled) {
					return originalRenderStream.call(me);
				}

				return renderStreamWithConstraints(me, buildConstraints(me, settings));
			});
		};

		frappe.ui.Capture.__av_tools_capture_override_installed = true;
		return true;
	}

	function retryInstall() {
		loadCaptureSettings();

		if (installCaptureOverride()) return;

		var attempts = 0;
		var interval = setInterval(function () {
			attempts += 1;

			if (installCaptureOverride() || attempts > 50) {
				clearInterval(interval);
			}
		}, 200);
	}

	$(retryInstall);
	$(document).on("app_ready startup", retryInstall);
})();
