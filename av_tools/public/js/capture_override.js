(function () {
	frappe.provide("av_tools.capture_override");
	var defaultCaptureSettings = {
		enabled: 0,
		force_web_capture_on_mobile: 0,
		ideal_width: 1920,
		ideal_height: 1080,
		min_width: 0,
		min_height: 0,
	};
	var captureSettingsCache = null;
	var captureSettingsPromise = null;

	function parsePositiveInt(value, fallback) {
		var parsed = parseInt(value, 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
	}

	function normalizeCaptureSettings(settings) {
		return {
			enabled: Boolean(Number(settings && settings.enabled)),
			force_web_capture_on_mobile: Boolean(
				Number(settings && settings.force_web_capture_on_mobile)
			),
			ideal_width: parsePositiveInt(settings && settings.ideal_width, 1920),
			ideal_height: parsePositiveInt(settings && settings.ideal_height, 1080),
			min_width: parsePositiveInt(settings && settings.min_width, 0),
			min_height: parsePositiveInt(settings && settings.min_height, 0),
		};
	}

	function getCaptureSettings() {
		return normalizeCaptureSettings(captureSettingsCache || defaultCaptureSettings);
	}

	function fetchCaptureSettings(forceRefresh) {
		if (!forceRefresh && captureSettingsCache) {
			return Promise.resolve(getCaptureSettings());
		}

		if (!forceRefresh && captureSettingsPromise) {
			return captureSettingsPromise;
		}

		captureSettingsPromise = new Promise(function (resolve) {
			frappe.call({
				method: "av_tools.av_tools_hooks.capture.get_capture_settings",
				callback: function (response) {
					captureSettingsCache = normalizeCaptureSettings(response.message || {});
					resolve(captureSettingsCache);
				},
				error: function () {
					captureSettingsCache = normalizeCaptureSettings(defaultCaptureSettings);
					resolve(captureSettingsCache);
				},
			});
		}).finally(function () {
			captureSettingsPromise = null;
		});

		return captureSettingsPromise;
	}

	function shouldForceAppWebCapture(settings) {
		return settings.enabled && settings.force_web_capture_on_mobile;
	}

	function shouldUseWebCaptureOnMobile(settings) {
		var sysdefaults = (frappe.boot && frappe.boot.sysdefaults) || {};
		return (
			shouldForceAppWebCapture(settings) ||
			Boolean(Number(sysdefaults.force_web_capture_mode_for_uploads))
		);
	}

	function buildTrackConstraints(capture, settings) {
		var constraints = {
			facingMode: {
				ideal: capture.facing_mode,
			},
		};

		if (settings.min_width || settings.ideal_width) {
			constraints.width = {};
			if (settings.min_width) {
				constraints.width.min = settings.min_width;
			}
			if (settings.ideal_width) {
				constraints.width.ideal = settings.ideal_width;
			}
		}

		if (settings.min_height || settings.ideal_height) {
			constraints.height = {};
			if (settings.min_height) {
				constraints.height.min = settings.min_height;
			}
			if (settings.ideal_height) {
				constraints.height.ideal = settings.ideal_height;
			}
		}

		if (settings.ideal_width || settings.ideal_height) {
			constraints.advanced = [
				{
					width: settings.ideal_width || undefined,
					height: settings.ideal_height || undefined,
				},
			];
		}

		return constraints;
	}

	function buildConstraints(capture, settings) {
		var video = buildTrackConstraints(capture, settings);

		return {
			video: video,
			audio: false,
		};
	}

	function applyTrackConstraints(track, capture, settings) {
		if (!track || typeof track.applyConstraints !== "function") {
			return Promise.resolve();
		}

		var constraints = buildTrackConstraints(capture, settings);
		return track.applyConstraints(constraints).catch(function (error) {
			console.warn("[av_tools] Failed to apply camera constraints", error);
		});
	}

	function blobToDataUrl(blob) {
		return new Promise(function (resolve, reject) {
			var reader = new FileReader();
			reader.onload = function () {
				resolve(reader.result);
			};
			reader.onerror = reject;
			reader.readAsDataURL(blob);
		});
	}

	function bitmapToPngDataUrl(bitmap) {
		var canvas = document.createElement("canvas");
		canvas.width = bitmap.width;
		canvas.height = bitmap.height;
		canvas.getContext("2d").drawImage(bitmap, 0, 0);

		if (typeof bitmap.close === "function") {
			bitmap.close();
		}

		return canvas.toDataURL("image/png");
	}

	function blobToPngDataUrl(blob) {
		if (typeof createImageBitmap === "function") {
			return createImageBitmap(blob).then(bitmapToPngDataUrl);
		}

		return blobToDataUrl(blob).then(function (dataUrl) {
			return new Promise(function (resolve, reject) {
				var image = new Image();
				image.onload = function () {
					var canvas = document.createElement("canvas");
					canvas.width = image.naturalWidth || image.width;
					canvas.height = image.naturalHeight || image.height;
					canvas.getContext("2d").drawImage(image, 0, 0);
					resolve(canvas.toDataURL("image/png"));
				};
				image.onerror = reject;
				image.src = dataUrl;
			});
		});
	}

	function captureStillImage(capture) {
		var fallbackImage = frappe._.get_data_uri(capture.video);
		var track =
			capture.stream && capture.stream.getVideoTracks && capture.stream.getVideoTracks()[0];

		if (!track || typeof ImageCapture !== "function") {
			return Promise.resolve(fallbackImage);
		}

		try {
			var imageCapture = new ImageCapture(track);
			if (typeof imageCapture.takePhoto !== "function") {
				return Promise.resolve(fallbackImage);
			}

			return imageCapture
				.takePhoto()
				.then(blobToPngDataUrl)
				.catch(function (error) {
					console.warn("[av_tools] Falling back to stream-frame capture", error);
					return fallbackImage;
				});
		} catch (error) {
			console.warn("[av_tools] Falling back to stream-frame capture", error);
			return Promise.resolve(fallbackImage);
		}
	}

	function logCaptureDetails(capture, stream, constraints) {
		if (!(frappe.boot && frappe.boot.developer_mode)) {
			return;
		}

		try {
			var track = stream.getVideoTracks()[0];
			var actualSettings = track && track.getSettings ? track.getSettings() : {};
			var capabilities = track && track.getCapabilities ? track.getCapabilities() : {};
			console.info("[av_tools] Camera capture override active", {
				requested_constraints: constraints,
				actual_settings: actualSettings,
				capabilities: capabilities,
				video_dimensions: {
					width: capture.video && capture.video.videoWidth,
					height: capture.video && capture.video.videoHeight,
				},
			});
		} catch (error) {
			console.warn("[av_tools] Failed to log camera capture details", error);
		}
	}

	function renderStreamWithConstraints(capture, constraints, settings) {
		return navigator.mediaDevices.getUserMedia(constraints).then(function (stream) {
			capture.stream = stream;
			var track = stream.getVideoTracks && stream.getVideoTracks()[0];

			return applyTrackConstraints(track, capture, settings).then(function () {
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
					return playPromise.then(function () {
						logCaptureDetails(capture, stream, constraints);
					});
				}

				logCaptureDetails(capture, stream, constraints);
				return undefined;
			});
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
		var originalSetupTakePhotoAction = proto.setup_take_photo_action;

		proto.show = function () {
			var me = this;
			return fetchCaptureSettings().then(function (settings) {
				me.__av_tools_capture_settings = settings;

				if (!shouldForceAppWebCapture(settings)) {
					return originalShow.call(me);
				}

				me.build_dialog();
				me.show_for_desktop();
				return undefined;
			});
		};

		proto.render_stream = function () {
			var me = this;
			return fetchCaptureSettings().then(function (settings) {
				me.__av_tools_capture_settings = settings;

				if (!settings.enabled) {
					return originalRenderStream.call(me);
				}

				return renderStreamWithConstraints(me, buildConstraints(me, settings), settings);
			});
		};

		proto.setup_take_photo_action = function () {
			var settings = this.__av_tools_capture_settings || getCaptureSettings();
			var me = this;

			if (!settings.enabled) {
				return originalSetupTakePhotoAction.call(this);
			}

			this.dialog.set_primary_action(__("Take Photo"), function () {
				captureStillImage(me).then(function (dataUrl) {
					me.images.push(dataUrl);
					me.setup_preview_action();
					me.update_count();
				});
			});
		};

		proto.setup_capture_action = function () {
			var me = this;

			this.dialog.set_secondary_action_label(__("Capture"));
			this.dialog.set_secondary_action(function () {
				fetchCaptureSettings().then(function (settings) {
					me.__av_tools_capture_settings = settings;
					if (frappe.is_mobile() && !shouldUseWebCaptureOnMobile(settings)) {
						me.show_for_mobile();
						return;
					}

					me.render_stream();
				});
			});
		};

		frappe.ui.Capture.__av_tools_capture_override_installed = true;
		return true;
	}

	function retryInstall() {
		if (installCaptureOverride()) {
			return;
		}

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
