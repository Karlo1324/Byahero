/**
 * Konduktor - AI Chat Assistant for ByaHero
 * Floating chatbot with data integration + LLM support
 */

(function() {
    'use strict';

    // ============================================
    // STATE
    // ============================================
    const state = {
        isOpen: false,
        messages: [],
        context: {
            currentPage: null,
            routeId: null,
            originId: null,
            destinationId: null,
            lastTripPlan: null
        },
        typingTimeout: null,
        llmMode: false,  // Will be detected from API
        llmAvailable: false
    };

    // ============================================
    // DOM ELEMENTS
    // ============================================
    let fab, panel, messagesContainer, quickActionsContainer, input, sendBtn, closeBtn, modeIndicator;

    function cacheElements() {
        fab = document.getElementById('konduktor-fab');
        panel = document.getElementById('konduktor-panel');
        messagesContainer = document.getElementById('konduktor-messages');
        quickActionsContainer = document.getElementById('konduktor-quick-actions');
        input = document.getElementById('konduktor-input');
        sendBtn = document.getElementById('konduktor-send');
        closeBtn = panel?.querySelector('.konduktor-close');
        modeIndicator = document.getElementById('konduktor-mode-indicator');
    }

    // ============================================
    // INITIALIZATION
    // ============================================
    function init() {
        cacheElements();
        if (!fab || !panel) return;

        bindEvents();
        detectContext();
        loadQuickActions();
        checkLLMStatus();
        addWelcomeMessage();
    }

    function bindEvents() {
        fab.addEventListener('click', togglePanel);
        closeBtn?.addEventListener('click', closePanel);
        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (state.isOpen && !panel.contains(e.target) && !fab.contains(e.target)) {
                closePanel();
            }
        });

        // Escape key closes
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && state.isOpen) closePanel();
        });
    }

    function detectContext() {
        const path = window.location.pathname;
        state.context.currentPage = path;

        // Extract context from page if available
        const routeSelect = document.getElementById('route');
        const originSelect = document.getElementById('origin');
        const destSelect = document.getElementById('destination');

        if (routeSelect?.value) state.context.routeId = parseInt(routeSelect.value);
        if (originSelect?.value) state.context.originId = parseInt(originSelect.value);
        if (destSelect?.value) state.context.destinationId = parseInt(destSelect.value);
    }

    // ============================================
    // LLM STATUS
    // ============================================
    async function checkLLMStatus() {
        try {
            const response = await fetch('/api/konduktor/status');
            const data = await response.json();
            state.llmAvailable = data.llm_available || false;
            state.llmMode = data.llm_mode || false;
            updateModeIndicator();
        } catch (e) {
            console.warn('Could not check LLM status');
        }
    }

    function updateModeIndicator() {
        if (!modeIndicator) return;
        if (state.llmAvailable) {
            modeIndicator.textContent = state.llmMode ? '🤖 LLM' : '🧠 Rule-based';
            modeIndicator.className = 'konduktor-mode-indicator active';
        } else {
            modeIndicator.textContent = '🧠 Rule-based';
            modeIndicator.className = 'konduktor-mode-indicator';
        }
    }

    // ============================================
    // PANEL CONTROL
    // ============================================
    function togglePanel() {
        state.isOpen ? closePanel() : openPanel();
    }

    function openPanel() {
        state.isOpen = true;
        panel.hidden = false;
        requestAnimationFrame(() => panel.classList.add('open'));
        fab.setAttribute('aria-expanded', 'true');
        input.focus();
        hideNotification();
    }

    function closePanel() {
        state.isOpen = false;
        panel.classList.remove('open');
        fab.setAttribute('aria-expanded', 'false');
        setTimeout(() => {
            if (!state.isOpen) panel.hidden = true;
        }, 220);
    }

    // ============================================
    // MESSAGES
    // ============================================
    function addWelcomeMessage() {
        const hour = new Date().getHours();
        const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
        addBotMessage(`${greeting}! I'm Konduktor, your ByaHero assistant. How can I help with your trip today?`);
    }

    function addBotMessage(text, options = {}) {
        const msg = createMessageElement('bot', text, options);
        messagesContainer.appendChild(msg);
        scrollToBottom();
        return msg;
    }

    function addUserMessage(text) {
        const msg = createMessageElement('user', text);
        messagesContainer.appendChild(msg);
        scrollToBottom();
        return msg;
    }

    function createMessageElement(sender, text, options = {}) {
        const wrapper = document.createElement('div');
        wrapper.className = `konduktor-message ${sender} ${options.error ? 'error' : ''}`;

        const avatar = document.createElement('div');
        avatar.className = 'konduktor-message-avatar';
        avatar.innerHTML = sender === 'bot'
            ? '<img class="konduktor-msg-avatar-img" src="/static/img/Monochrome Conductor Robot Badge.png" alt="Konduktor">'
            : '<svg class="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/></svg>';

        const bubble = document.createElement('div');
        bubble.className = 'konduktor-message-bubble';
        // Support markdown-like formatting
        bubble.innerHTML = formatMessage(text);

        const time = document.createElement('div');
        time.className = 'konduktor-message-time';
        time.textContent = formatTime(new Date());

        if (sender === 'bot') {
            wrapper.append(avatar, bubble, time);
        } else {
            wrapper.append(bubble, avatar, time);
        }

        state.messages.push({ sender, text, time: new Date() });
        return wrapper;
    }

    function formatMessage(text) {
        // Simple markdown-like formatting
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    function showTyping() {
        const typing = document.createElement('div');
        typing.className = 'konduktor-message bot konduktor-typing-msg';
        typing.innerHTML = `
            <div class="konduktor-message-avatar">
                <img class="konduktor-msg-avatar-img" src="/static/img/Monochrome Conductor Robot Badge.png" alt="Konduktor">
            </div>
            <div class="konduktor-typing">
                <span></span><span></span><span></span>
            </div>
        `;
        messagesContainer.appendChild(typing);
        scrollToBottom();
        return typing;
    }

    function hideTyping(typingEl) {
        if (typingEl?.parentNode) typingEl.parentNode.removeChild(typingEl);
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // ============================================
    // QUICK ACTIONS
    // ============================================
    function loadQuickActions() {
        const actions = getContextualQuickActions();
        quickActionsContainer.innerHTML = actions.map(action =>
            `<button class="konduktor-quick-action" data-action="${escapeHtml(action.value)}">${escapeHtml(action.label)}</button>`
        ).join('');

        quickActionsContainer.querySelectorAll('.konduktor-quick-action').forEach(btn => {
            btn.addEventListener('click', () => {
                input.value = btn.dataset.action;
                sendMessage();
            });
        });
    }

    function getContextualQuickActions() {
        const base = [
            { label: 'Plan a trip', value: 'Help me plan a trip from Kapatagan to Digos Terminal' },
            { label: 'Next bus times', value: 'When is the next bus at each stop?' },
            { label: 'How predictions work', value: 'How does the travel time prediction work?' }
        ];

        const page = state.context.currentPage;

        if (page === '/trip-planner' || page === '/') {
            return [
                { label: 'Best time to leave', value: 'What is the best time to leave today?' },
                { label: 'Current crowd level', value: 'What is the crowd level right now?' },
                { label: 'Explain my trip plan', value: 'Can you explain my trip plan results?' },
                ...base
            ];
        }

        if (page === '/historical-data') {
            return [
                { label: 'Show statistics', value: 'Show me statistics for all stops' },
                { label: 'Export data help', value: 'How do I export the arrival data?' },
                ...base
            ];
        }

        if (page === '/add-arrival') {
            return [
                { label: 'Record arrival help', value: 'How do I record a bus arrival?' },
                { label: 'Validation rules', value: 'What are the validation rules for arrivals?' },
                ...base
            ];
        }

        if (page === '/manage-locations') {
            return [
                { label: 'Add new stop', value: 'How do I add a new bus stop?' },
                { label: 'Manage routes', value: 'How do I add a new route?' },
                ...base
            ];
        }

        return base;
    }

    function updateQuickActions(suggestions) {
        quickActionsContainer.innerHTML = suggestions.map(s =>
            `<button class="konduktor-quick-action" data-action="${escapeHtml(s)}">${escapeHtml(s)}</button>`
        ).join('');

        quickActionsContainer.querySelectorAll('.konduktor-quick-action').forEach(btn => {
            btn.addEventListener('click', () => {
                input.value = btn.dataset.action;
                sendMessage();
            });
        });
    }

    // ============================================
    // CHAT API
    // ============================================
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        addUserMessage(text);
        input.value = '';
        input.disabled = true;
        sendBtn.disabled = true;

        const typingEl = showTyping();

        try {
            const response = await fetch('/api/konduktor/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    context: state.context
                })
            });

            const data = await response.json();
            hideTyping(typingEl);

            if (data.success) {
                addBotMessage(data.response);
                if (data.suggestions) {
                    updateQuickActions(data.suggestions);
                }
                if (data.tripPlan) {
                    state.context.lastTripPlan = data.tripPlan;
                }
                // Update session context from server (persistent across messages)
                if (data.context) {
                    state.context = { ...state.context, ...data.context };
                    console.log('Context updated:', state.context);
                }
                if (data.mode) {
                    state.llmMode = data.mode === 'llm';
                    updateModeIndicator();
                }
            } else {
                addBotMessage(data.error || 'Sorry, I encountered an error. Please try again.', { error: true });
            }
        } catch (err) {
            hideTyping(typingEl);
            addBotMessage('Connection error. Please check your connection and try again.', { error: true });
        } finally {
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
        }
    }

    // ============================================
    // NOTIFICATIONS
    // ============================================
    function showNotification(count = 1) {
        const badge = fab.querySelector('.konduktor-notification');
        if (badge) {
            badge.textContent = count > 9 ? '9+' : count;
            badge.classList.add('has-message');
        }
    }

    function hideNotification() {
        const badge = fab.querySelector('.konduktor-notification');
        if (badge) badge.classList.remove('has-message');
    }

    // ============================================
    // UTILITIES
    // ============================================
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================
    // PUBLIC API (for other scripts)
    // ============================================
    window.Konduktor = {
        open: openPanel,
        close: closePanel,
        sendMessage: (text) => {
            input.value = text;
            sendMessage();
        },
        updateContext: (ctx) => {
            state.context = { ...state.context, ...ctx };
            loadQuickActions();
        },
        notify: showNotification,
        setLLMMode: (enabled) => {
            state.llmMode = enabled;
            updateModeIndicator();
        }
    };

    // ============================================
    // AUTO-INIT
    // ============================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();