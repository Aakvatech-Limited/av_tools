frappe.pages["user_manager"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "User Manager",
		single_column: true,
	});

	frappe.require("https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.iife.js", () => {
		initApp(wrapper);
	});
};

function initApp(wrapper) {
	let $content = $(wrapper).find(".page-content");

	$content.html(`
        <style>
            :root {
                --gpt-bg: #ffffff;
                --gpt-sidebar-bg: #f7f7f8;
                --gpt-border: #e5e5e5;
                --gpt-text: #353740;
                --gpt-text-light: #6e6e80;
                --gpt-hover: #ececf1;
                --gpt-active: #e3e3e6;
                --gpt-green: #10a37f;
                --gpt-red: #ef4444;
                --gpt-blue: #2563eb;
                --gpt-success-bg: #f0fdf4;
                --gpt-error-bg: #fef2f2;
                --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
                --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.08);
                --shadow-lg: 0 8px 16px -4px rgba(0,0,0,0.1);
                --sidebar-width: 260px;
            }

            * { 
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            .um-layout { 
                display: flex; 
                height: calc(100vh - 60px); 
                background: var(--gpt-bg); 
                position: relative;
                overflow: hidden;
            }
            
            /* Sidebar */
            .um-sidebar { 
                width: var(--sidebar-width); 
                background: var(--gpt-sidebar-bg); 
                border-right: 1px solid var(--gpt-border); 
                display: flex; 
                flex-direction: column;
                transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                z-index: 1000;
                flex-shrink: 0;
            }
            
            .um-sidebar.collapsed {
                transform: translateX(-100%);
            }
            
            @media (max-width: 768px) {
                .um-sidebar {
                    position: fixed;
                    height: calc(100vh - 60px);
                    left: 0;
                    top: 60px;
                    z-index: 1001;
                    box-shadow: 2px 0 16px rgba(0,0,0,0.1);
                }
            }
            
            /* Toggle Button */
            .um-expand-btn {
                position: fixed;
                top: 70px;
                left: 12px;
                width: 44px;
                height: 44px;
                background: var(--gpt-bg);
                border: 1px solid var(--gpt-border);
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                z-index: 1002;
                box-shadow: var(--shadow-md);
                color: var(--gpt-text);
                transition: all 0.2s ease;
            }
            
            .um-expand-btn:hover {
                background: var(--gpt-hover);
                transform: scale(1.05);
            }
            
            .um-sidebar-header { 
                padding: 12px;
                border-bottom: 1px solid var(--gpt-border);
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .um-new-btn { 
                flex: 1;
                padding: 11px 14px; 
                background: var(--gpt-bg); 
                border: 1px solid var(--gpt-border); 
                border-radius: 8px; 
                font-size: 14px; 
                font-weight: 500;
                color: var(--gpt-text); 
                cursor: pointer; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                gap: 8px;
                box-shadow: var(--shadow-sm);
                transition: all 0.2s ease;
            }
            .um-new-btn:hover { 
                background: var(--gpt-hover); 
                transform: translateY(-1px);
            }
            
            .um-toggle-btn {
                width: 32px;
                height: 32px;
                padding: 0;
                background: var(--gpt-bg);
                border: 1px solid var(--gpt-border);
                border-radius: 6px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                color: var(--gpt-text);
                transition: all 0.2s ease;
                flex-shrink: 0;
            }
            .um-toggle-btn:hover {
                background: var(--gpt-hover);
            }
            
            .um-history { 
                flex: 1; 
                overflow-y: auto; 
                padding: 8px;
            }
            .um-history::-webkit-scrollbar { width: 5px; }
            .um-history::-webkit-scrollbar-thumb { 
                background: #d1d5db; 
                border-radius: 10px;
            }
            
            .um-history-item { 
                padding: 12px 14px; 
                margin-bottom: 4px; 
                border-radius: 8px; 
                cursor: pointer; 
                font-size: 13px; 
                color: var(--gpt-text);
                position: relative;
                transition: all 0.2s ease;
            }
            .um-history-item::before {
                content: '';
                position: absolute;
                left: 0;
                top: 0;
                width: 3px;
                height: 100%;
                background: var(--gpt-green);
                transform: scaleY(0);
                transition: transform 0.2s ease;
                border-radius: 0 2px 2px 0;
            }
            .um-history-item:hover { 
                background: var(--gpt-hover); 
            }
            .um-history-item.active { 
                background: var(--gpt-active); 
                font-weight: 500;
            }
            .um-history-item.active::before { transform: scaleY(1); }
            .um-history-email { 
                font-weight: 500; 
                margin-bottom: 4px; 
                white-space: nowrap; 
                overflow: hidden; 
                text-overflow: ellipsis; 
            }
            .um-history-meta { 
                display: flex; 
                justify-content: space-between; 
                align-items: center;
                font-size: 11px; 
                color: var(--gpt-text-light); 
                gap: 8px;
            }
            .um-history-action { 
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
            }
            .um-history-action.enable { background: var(--gpt-success-bg); color: var(--gpt-green); }
            .um-history-action.disable { background: var(--gpt-error-bg); color: var(--gpt-red); }
            
            /* Main Content */
            .um-main { 
                flex: 1; 
                display: flex; 
                flex-direction: column;
                min-width: 0;
            }
            
            .um-results { 
                flex: 1; 
                overflow-y: auto; 
                padding: 80px 24px 200px 24px; 
                scroll-behavior: smooth;
            }
            
            @media (max-width: 768px) {
                .um-results {
                    padding: 80px 16px 220px 16px;
                }
            }
            
            .um-results::-webkit-scrollbar { width: 6px; }
            .um-results::-webkit-scrollbar-thumb { 
                background: var(--gpt-border); 
                border-radius: 10px;
            }
            
            /* Input Bar */
            .um-input-bar { 
                position: fixed; 
                bottom: 0; 
                left: 0;
                right: 0; 
                background: transparent;
                padding: 20px; 
                z-index: 999;
                transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            @media (min-width: 769px) {
                .um-input-bar.sidebar-open {
                    left: var(--sidebar-width);
                }
            }
            
            @media (max-width: 768px) {
                .um-input-bar {
                    padding: 16px;
                }
            }
            
            .um-input-wrapper {
                max-width: 900px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.98);
                border: 1px solid var(--gpt-border);
                border-radius: 24px;
                padding: 18px 20px;
                box-shadow: 
                    0 8px 32px rgba(0, 0, 0, 0.12),
                    0 2px 8px rgba(0, 0, 0, 0.08);
                backdrop-filter: blur(20px);
            }
            
            @media (max-width: 768px) {
                .um-input-wrapper {
                    padding: 14px 16px;
                    border-radius: 20px;
                }
            }
            
            .um-container { 
                display: flex; 
                gap: 10px; 
                align-items: stretch;
            }
            
            @media (max-width: 768px) {
                .um-container {
                    flex-direction: column;
                    gap: 10px;
                }
            }
            
            .um-group { 
                flex: 1; 
                display: flex;
                gap: 8px;
                align-items: center;
            }
            
            .um-group select, .um-group input { 
                flex: 1;
                height: 46px; 
                border: 1px solid var(--gpt-border); 
                border-radius: 10px; 
                padding: 0 14px; 
                font-size: 14px; 
                color: var(--gpt-text); 
                background: var(--gpt-bg);
                box-shadow: var(--shadow-sm);
                transition: all 0.2s ease;
            }
            
            @media (max-width: 768px) {
                .um-group select, .um-group input {
                    height: 44px;
                    font-size: 15px;
                }
            }
            
            .um-group select:focus, .um-group input:focus { 
                outline: none; 
                border-color: var(--gpt-text);
                box-shadow: 0 0 0 3px rgba(53, 55, 64, 0.08);
            }
            
            .um-icon-btn {
                width: 32px;
                height: 32px;
                padding: 0;
                background: var(--gpt-bg);
                border: 1px solid var(--gpt-border);
                border-radius: 6px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                color: var(--gpt-text);
                font-size: 16px;
                transition: all 0.2s ease;
                flex-shrink: 0;
            }
            
            .um-icon-btn:hover {
                background: var(--gpt-hover);
                transform: scale(1.05);
            }
            
            .um-buttons { 
                display: flex; 
                gap: 10px;
            }
            
            @media (max-width: 768px) {
                .um-buttons {
                    width: 100%;
                }
            }
            
            .um-btn { 
                height: 46px; 
                min-width: 115px; 
                border: none;
                border-radius: 10px; 
                font-size: 14px; 
                font-weight: 600; 
                cursor: pointer; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                gap: 6px; 
                color: white;
                position: relative;
                overflow: hidden;
                transition: all 0.3s ease;
            }
            
            @media (max-width: 768px) {
                .um-btn {
                    flex: 1;
                    height: 44px;
                }
            }
            
            .um-btn.btn-disable {
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
            }
            
            .um-btn.btn-disable::before {
                content: '';
                position: absolute;
                inset: 0;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
                transform: translateX(-100%);
                transition: transform 0.6s ease;
            }
            
            .um-btn.btn-disable:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
            }
            .um-btn.btn-disable:hover:not(:disabled)::before { 
                transform: translateX(100%); 
            }
            
            .um-btn.btn-enable {
                background: linear-gradient(135deg, #10a37f 0%, #059669 100%);
                box-shadow: 0 4px 12px rgba(16, 163, 127, 0.3);
            }
            
            .um-btn.btn-enable::before {
                content: '';
                position: absolute;
                inset: 0;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
                transform: translateX(-100%);
                transition: transform 0.6s ease;
            }
            
            .um-btn.btn-enable:hover:not(:disabled)::before { 
                transform: translateX(100%); 
            }
            .um-btn.btn-enable:hover:not(:disabled) {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(16, 163, 127, 0.4);
            }
            
            .um-btn:disabled { 
                opacity: 0.6; 
                cursor: not-allowed;
                transform: none !important;
            }
            
            /* Result Cards */
            .um-card { 
                max-width: 900px; 
                margin: 0 auto 20px; 
                background: var(--gpt-bg); 
                border: 1px solid var(--gpt-border); 
                border-radius: 12px; 
                padding: 24px;
                box-shadow: var(--shadow-sm);
                animation: slideIn 0.3s ease-out;
            }
            
            @media (max-width: 768px) {
                .um-card {
                    padding: 18px;
                }
            }
            
            @keyframes slideIn { 
                from { opacity: 0; transform: translateY(-10px); } 
                to { opacity: 1; transform: translateY(0); } 
            }
            
            .um-card:hover { 
                box-shadow: var(--shadow-md);
            }
            
            .um-header { 
                display: flex; 
                justify-content: space-between; 
                align-items: flex-start; 
                margin-bottom: 18px; 
                padding-bottom: 14px; 
                border-bottom: 1px solid var(--gpt-border);
                gap: 12px;
            }
            
            .um-email { 
                font-size: 16px; 
                font-weight: 700; 
                color: var(--gpt-text);
                word-break: break-word;
                flex: 1;
            }
            
            .um-time { 
                font-size: 12px; 
                color: var(--gpt-text-light);
                white-space: nowrap;
            }
            
            .um-summary { 
                display: flex; 
                gap: 14px; 
                margin-bottom: 18px; 
                padding: 12px 14px; 
                background: var(--gpt-sidebar-bg); 
                border-radius: 8px; 
                font-size: 13px; 
                color: var(--gpt-text-light);
                flex-wrap: wrap;
            }
            
            .um-summary strong { 
                color: var(--gpt-text); 
                font-weight: 600;
            }
            
            .um-site { 
                padding: 14px; 
                margin-bottom: 10px; 
                border: 1px solid var(--gpt-border); 
                border-radius: 8px; 
                display: flex; 
                justify-content: space-between; 
                align-items: flex-start; 
                background: var(--gpt-bg);
                gap: 12px;
                transition: all 0.2s ease;
            }
            
            @media (max-width: 768px) {
                .um-site {
                    flex-direction: column;
                }
            }
            
            .um-site:hover { 
                background: var(--gpt-sidebar-bg);
            }
            
            .um-site-info { 
                flex: 1; 
                min-width: 0; 
            }
            
            .um-site-name { 
                font-size: 14px; 
                font-weight: 700; 
                color: var(--gpt-text); 
                margin-bottom: 5px;
            }
            
            .um-site-url { 
                font-size: 11px; 
                color: var(--gpt-text-light); 
                margin-bottom: 5px;
                word-break: break-all;
                font-family: monospace;
            }
            
            .um-site-msg { 
                font-size: 13px; 
                color: var(--gpt-text-light); 
            }
            
            .um-badge { 
                padding: 5px 10px; 
                border-radius: 5px; 
                font-size: 10px; 
                font-weight: 700; 
                text-transform: uppercase; 
                white-space: nowrap;
            }
            
            .um-badge-success { background: var(--gpt-success-bg); color: var(--gpt-green); }
            .um-badge-error { background: var(--gpt-error-bg); color: var(--gpt-red); }
            .um-badge-skipped { background: var(--gpt-hover); color: var(--gpt-text-light); }
            
            .um-empty { 
                max-width: 480px; 
                margin: 100px auto; 
                text-align: center; 
                color: var(--gpt-text-light);
                padding: 0 20px;
            }
            
            .um-empty-icon { 
                font-size: 48px; 
                margin-bottom: 16px; 
                opacity: 0.4;
            }
            
            .um-empty-text { 
                font-size: 15px;
                line-height: 1.5;
            }
            
            /* Overlay */
            .um-overlay {
                display: none;
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.4);
                z-index: 1000;
                backdrop-filter: blur(2px);
                animation: fadeIn 0.2s ease-out;
            }
            
            .um-overlay.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* Modal */
            .um-modal-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 2000;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                animation: fadeIn 0.2s ease-out;
            }
            
            .um-modal {
                background: var(--gpt-bg);
                border-radius: 16px;
                box-shadow: var(--shadow-lg);
                max-width: 900px;
                width: 100%;
                max-height: 90vh;
                display: flex;
                flex-direction: column;
                animation: scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            }
            
            @keyframes scaleIn {
                from { opacity: 0; transform: scale(0.95); }
                to { opacity: 1; transform: scale(1); }
            }
            
            .um-modal-header {
                padding: 20px 24px;
                border-bottom: 1px solid var(--gpt-border);
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            
            .um-modal-title {
                font-size: 18px;
                font-weight: 700;
                color: var(--gpt-text);
            }
            
            .um-modal-close {
                width: 32px;
                height: 32px;
                border-radius: 6px;
                border: 1px solid var(--gpt-border);
                background: var(--gpt-bg);
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                color: var(--gpt-text);
                font-size: 18px;
                transition: all 0.2s ease;
            }
            
            .um-modal-close:hover {
                background: var(--gpt-hover);
            }
            
            .um-modal-body {
                flex: 1;
                overflow-y: auto;
                padding: 24px;
            }
            
            .um-modal-body::-webkit-scrollbar { width: 6px; }
            .um-modal-body::-webkit-scrollbar-thumb { 
                background: var(--gpt-border); 
                border-radius: 10px;
            }
            
            .um-form-group {
                margin-bottom: 20px;
            }
            
            .um-label {
                display: block;
                font-size: 14px;
                font-weight: 600;
                color: var(--gpt-text);
                margin-bottom: 8px;
            }
            
            .um-input, .um-textarea {
                width: 100%;
                padding: 10px 14px;
                border: 1px solid var(--gpt-border);
                border-radius: 8px;
                font-size: 14px;
                color: var(--gpt-text);
                background: var(--gpt-bg);
                transition: all 0.2s ease;
            }
            
            .um-input:focus, .um-textarea:focus {
                outline: none;
                border-color: var(--gpt-text);
                box-shadow: 0 0 0 3px rgba(53, 55, 64, 0.08);
            }
            
            .um-textarea {
                resize: vertical;
                min-height: 80px;
            }
            
            .um-divider {
                height: 1px;
                background: var(--gpt-border);
                margin: 24px 0;
            }
            
            .um-section-title {
                font-size: 16px;
                font-weight: 700;
                color: var(--gpt-text);
                margin-bottom: 16px;
            }
            
            .um-table {
                width: 100%;
                border-collapse: collapse;
                border: 1px solid var(--gpt-border);
                border-radius: 8px;
                overflow: hidden;
                margin-bottom: 16px;
            }
            
            .um-table thead {
                background: var(--gpt-sidebar-bg);
            }
            
            .um-table th {
                padding: 10px 12px;
                text-align: left;
                font-size: 12px;
                font-weight: 600;
                color: var(--gpt-text);
                border-bottom: 1px solid var(--gpt-border);
            }
            
            .um-table td {
                padding: 10px 12px;
                border-bottom: 1px solid var(--gpt-border);
            }
            
            .um-table tbody tr:last-child td {
                border-bottom: none;
            }
            
            .um-table input[type="text"],
            .um-table input[type="password"] {
                width: 100%;
                padding: 6px 10px;
                border: 1px solid var(--gpt-border);
                border-radius: 6px;
                font-size: 13px;
            }
            
            .um-table input[type="checkbox"] {
                width: 18px;
                height: 18px;
                cursor: pointer;
            }
            
            .um-add-btn {
                padding: 8px 16px;
                background: var(--gpt-bg);
                border: 1px solid var(--gpt-border);
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
                color: var(--gpt-text);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .um-add-btn:hover {
                background: var(--gpt-hover);
            }
            
            .um-modal-footer {
                padding: 16px 24px;
                border-top: 1px solid var(--gpt-border);
                display: flex;
                gap: 10px;
                justify-content: flex-end;
            }
            
            .um-modal-btn {
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                border: none;
            }
            
            .um-modal-btn-secondary {
                background: var(--gpt-bg);
                border: 1px solid var(--gpt-border);
                color: var(--gpt-text);
            }
            
            .um-modal-btn-secondary:hover {
                background: var(--gpt-hover);
            }
            
            .um-modal-btn-primary {
                background: var(--gpt-blue);
                color: white;
                box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
            }
            
            .um-modal-btn-primary:hover {
                background: #1d4ed8;
                box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
            }
            
            .um-remove-btn {
                padding: 4px 10px;
                background: var(--gpt-error-bg);
                border: 1px solid var(--gpt-red);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                color: var(--gpt-red);
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .um-remove-btn:hover {
                background: var(--gpt-red);
                color: white;
            }
        </style>

        <div id="app" v-scope @vue:mounted="init">
            <!-- Expand Button -->
            <button 
                v-if="sidebarCollapsed"
                @click="toggleSidebar" 
                class="um-expand-btn">
                ☰
            </button>

            <!-- Overlay -->
            <div 
                class="um-overlay" 
                :class="{active: !sidebarCollapsed && isMobile}"
                @click="toggleSidebar">
            </div>

            <div class="um-layout">
                <!-- Sidebar -->
                <div class="um-sidebar" :class="{collapsed: sidebarCollapsed}">
                    <div class="um-sidebar-header">
                        <button @click="clearSession" class="um-new-btn">
                            <span>✚</span> New Session
                        </button>
                        <button 
                            @click="toggleSidebar" 
                            class="um-toggle-btn">
                            ✕
                        </button>
                    </div>
                    <div class="um-history">
                        <div 
                            v-for="log in history" 
                            :key="log.name"
                            @click="loadLogDetail(log)"
                            class="um-history-item"
                            :class="{active: selectedLog === log.name}">
                            <div class="um-history-email">{{ log.email }}</div>
                            <div class="um-history-meta">
                                <span class="um-history-action" :class="log.action.toLowerCase()">
                                    {{ log.action }}
                                </span>
                                <span>{{ formatHistoryTime(log.timestamp) }}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Main Content -->
                <div class="um-main">
                    <div class="um-results">
                        <div v-if="currentDetail === null" class="um-empty">
                            <div class="um-empty-icon">💬</div>
                            <div class="um-empty-text">
                                Enter a user email and select an action to get started
                            </div>
                        </div>

                        <div v-if="currentDetail" class="um-card">
                            <div class="um-header">
                                <div class="um-email">{{ currentDetail.email }}</div>
                                <div class="um-time">{{ formatTime(currentDetail.timestamp) }}</div>
                            </div>

                            <div class="um-summary">
                                <div>Action: <strong :style="{color: currentDetail.action === 'Disable' ? 'var(--gpt-red)' : 'var(--gpt-green)'}">
                                    {{ currentDetail.action }}
                                </strong></div>
                                <div>Sites: <strong>{{ currentDetail.total_sites }}</strong></div>
                                <div>Success: <strong style="color: var(--gpt-green)">{{ currentDetail.successful }}</strong></div>
                                <div>Failed: <strong style="color: var(--gpt-red)">{{ currentDetail.failed }}</strong></div>
                                <div>Skipped: <strong>{{ currentDetail.skipped }}</strong></div>
                            </div>

                            <div v-for="site in currentDetail.sites" :key="site.site_name" class="um-site">
                                <div class="um-site-info">
                                    <div class="um-site-name">{{ site.site_name }}</div>
                                    <div class="um-site-url">{{ site.site_url }}</div>
                                    <div class="um-site-msg">{{ site.message }}</div>
                                </div>
                                <div class="um-badge" 
                                    :class="{
                                        'um-badge-success': site.status === 'success',
                                        'um-badge-error': site.status === 'error',
                                        'um-badge-skipped': site.status === 'skipped'
                                    }">
                                    {{ site.status }}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Input Bar -->
                    <div class="um-input-bar" :class="{'sidebar-open': !sidebarCollapsed && !isMobile}">
                        <div class="um-input-wrapper">
                            <div class="um-container">
                                <div class="um-group">
                                    <select v-model="siteConfig">
                                        <option value="">Select configuration...</option>
                                        <option v-for="config in configs" :value="config.name">
                                            {{ config.title || config.name }}
                                        </option>
                                    </select>
                                    <button @click="newConfiguration" class="um-icon-btn" title="New Configuration">+</button>
                                    <button v-if="siteConfig" @click="editConfiguration" class="um-icon-btn" title="Edit Configuration">✎</button>
                                </div>

                                <div class="um-group">
                                    <input 
                                        v-model="email" 
                                        type="email" 
                                        placeholder="user@example.com"
                                        @keyup.enter="disableUser"
                                    />
                                </div>

                                <div class="um-buttons">
                                    <button @click="disableUser" :disabled="loading" class="um-btn btn-disable">
                                        <span v-if="loading && actionType === 'disable'">⏳</span>
                                        <span v-else>↓</span>
                                        Disable
                                    </button>
                                    <button @click="enableUser" :disabled="loading" class="um-btn btn-enable">
                                        <span v-if="loading && actionType === 'enable'">⏳</span>
                                        <span v-else>↑</span>
                                        Enable
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Configuration Modal -->
            <div v-if="showSiteDialog" class="um-modal-overlay" @click.self="showSiteDialog = false">
                <div class="um-modal">
                    <div class="um-modal-header">
                        <h3 class="um-modal-title">{{ isEditMode ? 'Edit' : 'New' }} Site Configuration</h3>
                        <button class="um-modal-close" @click="showSiteDialog = false">✕</button>
                    </div>
                    
                    <div class="um-modal-body">
                        <div class="um-form-group">
                            <label class="um-label">Title *</label>
                            <input type="text" class="um-input" v-model="currentConfig.title" placeholder="Production Sites">
                        </div>
                        
                        <div class="um-form-group">
                            <label class="um-label">Description</label>
                            <textarea class="um-textarea" v-model="currentConfig.description" placeholder="Enter description..."></textarea>
                        </div>
                        
                        <div class="um-divider"></div>
                        
                        <h4 class="um-section-title">Sites</h4>
                        
                        <table class="um-table">
                            <thead>
                                <tr>
                                    <th style="width: 60px;">Enabled</th>
                                    <th>Site Name</th>
                                    <th>Site URL</th>
                                    <th>API Key</th>
                                    <th>API Secret</th>
                                    <th style="width: 80px;"></th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="(site, index) in currentConfig.sites" :key="index">
                                    <td><input type="checkbox" v-model="site.enabled"></td>
                                    <td><input type="text" v-model="site.site_name" placeholder="Site 1"></td>
                                    <td><input type="text" v-model="site.site_url" placeholder="https://site1.com"></td>
                                    <td><input type="text" v-model="site.api_key" placeholder="API Key"></td>
                                    <td><input type="password" v-model="site.api_secret" placeholder="Secret"></td>
                                    <td><button @click="removeSite(index)" class="um-remove-btn">Remove</button></td>
                                </tr>
                            </tbody>
                        </table>
                        
                        <button @click="addSite" class="um-add-btn">+ Add Site</button>
                    </div>
                    
                    <div class="um-modal-footer">
                        <button class="um-modal-btn um-modal-btn-secondary" @click="showSiteDialog = false">Cancel</button>
                        <button class="um-modal-btn um-modal-btn-primary" @click="saveConfiguration">Save Configuration</button>
                    </div>
                </div>
            </div>
        </div>
    `);

	PetiteVue.createApp({
		email: "",
		siteConfig: "",
		configs: [],
		history: [],
		currentDetail: null,
		selectedLog: null,
		loading: false,
		actionType: "",
		sidebarCollapsed: false,
		isMobile: window.innerWidth <= 768,
		showSiteDialog: false,
		isEditMode: false,
		currentConfig: {
			title: "",
			description: "",
			sites: [],
		},

		init() {
			this.loadConfigs();
			this.loadHistory();

			window.addEventListener("resize", () => {
				const mobile = window.innerWidth <= 768;
				if (this.isMobile && !mobile) {
					this.sidebarCollapsed = false;
				} else if (!this.isMobile && mobile) {
					this.sidebarCollapsed = true;
				}
				this.isMobile = mobile;
			});

			if (this.isMobile) {
				this.sidebarCollapsed = true;
			}
		},

		toggleSidebar() {
			this.sidebarCollapsed = !this.sidebarCollapsed;
		},

		async loadConfigs() {
			const res = await frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Site Configuration",
					fields: ["name", "title"],
					limit_page_length: 0,
				},
			});
			this.configs = res.message || [];
		},

		async loadHistory() {
			const res = await frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "User Manager Log",
					fields: ["name", "email", "action", "timestamp"],
					order_by: "timestamp desc",
					limit_page_length: 50,
				},
			});
			this.history = res.message || [];
		},

		async loadLogDetail(log) {
			this.selectedLog = log.name;

			if (this.isMobile) {
				this.sidebarCollapsed = true;
			}

			const res = await frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "User Manager Log",
					name: log.name,
				},
			});

			if (res.message) {
				const logData = res.message;
				let sites = [];

				try {
					const resultJson = JSON.parse(logData.result_json);
					sites = resultJson.results || [];
				} catch (e) {
					console.error("Failed to parse result_json", e);
				}

				this.currentDetail = {
					email: logData.email,
					action: logData.action,
					timestamp: logData.timestamp,
					total_sites: logData.total_sites || 0,
					successful: logData.successful || 0,
					failed: logData.failed || 0,
					skipped: logData.skipped || 0,
					sites: sites,
				};
			}
		},

		clearSession() {
			this.currentDetail = null;
			this.selectedLog = null;
			this.email = "";
			if (this.isMobile) {
				this.sidebarCollapsed = true;
			}
		},

		async disableUser() {
			if (!this.validate()) return;
			await this.executeAction(
				"Disable",
				"av_tools.api.multi_site_orchestrator.disable_user_on_all_sites"
			);
		},

		async enableUser() {
			if (!this.validate()) return;
			await this.executeAction(
				"Enable",
				"av_tools.api.multi_site_orchestrator.enable_user_on_all_sites"
			);
		},

		validate() {
			if (!this.email) {
				frappe.msgprint("Please enter user email");
				return false;
			}
			if (!this.siteConfig) {
				frappe.msgprint("Please select site configuration");
				return false;
			}
			return true;
		},

		async executeAction(action, method) {
			this.loading = true;
			this.actionType = action.toLowerCase();

			try {
				const res = await frappe.call({
					method: method,
					args: {
						email: this.email,
						site_configuration_name: this.siteConfig,
					},
				});

				if (res.message) {
					const result = res.message;
					await this.saveLog(action, result);
					await this.loadHistory();

					if (this.history.length > 0) {
						await this.loadLogDetail(this.history[0]);
					}

					this.email = "";
				}
			} catch (error) {
				frappe.msgprint("Failed to execute action");
			} finally {
				this.loading = false;
				this.actionType = "";
			}
		},

		async saveLog(action, result) {
			const stats = this.calculateStats(result.results);

			await frappe.call({
				method: "frappe.client.insert",
				args: {
					doc: {
						doctype: "User Manager Log",
						email: result.email,
						action: action,
						site_configuration: result.configuration,
						total_sites: result.total_sites,
						successful: stats.successful,
						failed: stats.failed,
						skipped: stats.skipped,
						result_json: JSON.stringify(result),
					},
				},
			});
		},

		calculateStats(results) {
			return {
				successful: results.filter((r) => r.status === "success").length,
				failed: results.filter((r) => r.status === "error").length,
				skipped: results.filter((r) => r.status === "skipped").length,
			};
		},

		formatTime(timestamp) {
			return new Date(timestamp).toLocaleString("en-US", {
				month: "short",
				day: "numeric",
				year: "numeric",
				hour: "2-digit",
				minute: "2-digit",
			});
		},

		formatHistoryTime(timestamp) {
			const date = new Date(timestamp);
			const now = new Date();
			const diffMs = now - date;
			const diffMins = Math.floor(diffMs / 60000);
			const diffHours = Math.floor(diffMs / 3600000);
			const diffDays = Math.floor(diffMs / 86400000);

			if (diffMins < 1) return "Just now";
			if (diffMins < 60) return `${diffMins}m ago`;
			if (diffHours < 24) return `${diffHours}h ago`;
			if (diffDays < 7) return `${diffDays}d ago`;
			return date.toLocaleDateString();
		},

		newConfiguration() {
			this.isEditMode = false;
			this.currentConfig = {
				title: "",
				description: "",
				sites: [],
			};
			this.showSiteDialog = true;
		},

		async editConfiguration() {
			if (!this.siteConfig) return;
			this.isEditMode = true;

			const res = await frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Site Configuration",
					name: this.siteConfig,
				},
			});

			if (res.message) {
				this.currentConfig = {
					name: res.message.name,
					title: res.message.title,
					description: res.message.description,
					sites: res.message.sites || [],
				};
				this.showSiteDialog = true;
			}
		},

		addSite() {
			this.currentConfig.sites.push({
				enabled: 1,
				site_name: "",
				site_url: "",
				api_key: "",
				api_secret: "",
			});
		},

		removeSite(index) {
			this.currentConfig.sites.splice(index, 1);
		},

		async saveConfiguration() {
			if (!this.currentConfig.title) {
				frappe.msgprint("Title is required");
				return;
			}

			try {
				if (this.isEditMode) {
					await frappe.call({
						method: "frappe.client.set_value",
						args: {
							doctype: "Site Configuration",
							name: this.currentConfig.name,
							fieldname: {
								title: this.currentConfig.title,
								description: this.currentConfig.description,
								sites: this.currentConfig.sites,
							},
						},
					});
				} else {
					const res = await frappe.call({
						method: "frappe.client.insert",
						args: {
							doc: {
								doctype: "Site Configuration",
								title: this.currentConfig.title,
								description: this.currentConfig.description,
								sites: this.currentConfig.sites,
							},
						},
					});
					if (res.message) {
						this.siteConfig = res.message.name;
					}
				}

				await this.loadConfigs();
				this.showSiteDialog = false;
				frappe.msgprint("Configuration saved successfully");
			} catch (error) {
				frappe.msgprint("Failed to save configuration");
			}
		},
	}).mount("#app");
}
