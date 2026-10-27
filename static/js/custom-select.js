/* =============================================
   Custom Select Dropdown Logic
   Auto-enhances every <select> on the page
   keeping the original element as the source of truth
   ============================================= */

(function () {
    // Sink for all open panels
    const openPanels = document.querySelectorAll('.custom-select-container.is-open');

    const closeAllPanels = function () {
        openPanels.forEach(function (panel) {
            panel.classList.remove('is-open');
        });
    };

    // Close on outside click
    document.addEventListener('click', function (event) {
        if (!event.target.closest('.custom-select-container')) {
            closeAllPanels();
        }
    });

    // Escape closes
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeAllPanels();
        }
    });

    /** Walk the container tree and wrap any un-enhanced selects */
    function enhanceSelects() {
        const containers = document.querySelectorAll('.custom-select-container');
        containers.forEach(function (container) {
            // Already wrapped or no select inside
            if (container.dataset.wrapped === 'true') return;

            const select = container.querySelector('select');
            if (!select || select.dataset.enhanced === 'true') return;

            wrapSelect(container, select);
        });
    }

    /** Replace the select with trigger + hidden + panel */
    function wrapSelect(container, select) {
        // Can't easily clone without losing our additions,
        // but we only run once per element instance via dataset flags.

        // --- Trigger ---
        const trigger = document.createElement('div');
        trigger.className = 'custom-select-trigger';
        trigger.setAttribute('tabindex', select.getAttribute('tabindex') === null ? '0' : select.getAttribute('tabindex'));
        trigger.setAttribute('role', 'combobox');
        trigger.setAttribute('aria-expanded', 'false');

        // Value label
        const valueText = select.options[select.selectedIndex]
            ? select.options[select.selectedIndex].text
            : 'Select...';
        trigger.setAttribute('aria-valuenow', String(select.selectedIndex));

        // --- Hidden original ---
        const hidden = document.createElement('select');
        hidden.className = 'custom-select-hidden';
        hidden.id = select.id;
        hidden.name = select.name;
        hidden.required = select.hasAttribute('required');
        hidden.disabled = select.disabled;
        for (let i = 0; i < select.options.length; i++) {
            const opt = select.options[i];
            const o = document.createElement('option');
            o.value = opt.value;
            o.disabled = opt.disabled;
            o.textContent = opt.textContent;
            hidden.appendChild(o);
        }

        // --- Options panel ---
        const panel = document.createElement('div');
        panel.className = 'custom-select-options';
        panel.role = 'listbox';

        // Render visible options
        renderOptions(panel, hidden);

        // --- Assemble ---
        container.classList.add('custom-select-container');
        container.dataset.wrapped = 'true';
        container.innerHTML = ''; // Remove existing select
        container.appendChild(hidden);
        container.appendChild(panel);
        container.appendChild(trigger);

        // --- Events ---
        trigger.addEventListener('mousedown', function (event) {
            // Prevent the browser native dropdown from firing
            event.preventDefault();
        });

        trigger.addEventListener('click', function (event) {
            event.preventDefault();
            togglePanel(container);
            trigger.focus();
        });

        trigger.addEventListener('focus', function () {
            if (select.disabled) {
                trigger.classList.add('is-disabled');
            } else {
                trigger.classList.remove('is-disabled');
            }
        });

        // Key handling on the trigger
        trigger.addEventListener('keydown', function (event) {
            handleKeydown(event, container, trigger, panel, hidden);
        });

        hidden.addEventListener('change', function () {
            onValueChange(container, hidden);
        });

        hidden.addEventListener('input', function () {
            onValueChange(container, hidden);
        });

        // Sync disabled state from triggers manually
        syncDisabled(container, select);
    }

    /** Render all non-disabled options into the panel */
    function renderOptions(panel, select) {
        // Clear stale nodes
        panel.innerHTML = '';

        const options = select.options;
        const listboxItems = [];

        for (let i = 0; i < options.length; i++) {
            const opt = options[i];
            if (opt.disabled) continue;

            const item = document.createElement('div');
            item.className = 'custom-select-option';
            item.textContent = opt.textContent;
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', opt.selected ? 'true' : 'false');
            item.dataset.value = opt.value;

            item.addEventListener('mousedown', function (event) {
                event.preventDefault();
                opt.selected = true;
                hiddenSetSelected(select, valueOfOption(opt));
                updateTrigger(container, select);
                panel.setAttribute('aria-activedescendant', '');
                closeAllPanels();
            });

            item.addEventListener('mouseenter', function () {
                highlightItem(panel, i);
            });

            listboxItems.push(item);
        }

        panel.appendChild(...listboxItems);
    }

    /** Toggle open / close */
    function togglePanel(container) {
        const isOpen = container.classList.contains('is-open');
        closeAllPanels();
        if (!isOpen) {
            container.classList.add('is-open');
            triggerFocusStyles(container);
            highlightFirstItem(container);
        }
    }

    /** Mirror select state into trigger text, hidden options, aria-valuenow */
    function updateTrigger(container, select) {
        const trigger = container.querySelector('.custom-select-trigger');
        const hidden = container.querySelector('.custom-select-hidden');
        if (!trigger || !hidden) return;

        const idx = select.selectedIndex;
        const text = idx >= 0 ? select.options[idx].text : 'Select...';

        trigger.textContent = text;
        trigger.setAttribute('aria-valuenow', String(idx));
        trigger.setAttribute('aria-expanded', 'true');

        // Refresh option classes
        const items = container.querySelectorAll('.custom-select-option');
        items.forEach(function (el) {
            const val = el.dataset.value;
            const isSelected = hidden.value === val && hidden.selectedIndex >= 0;
            el.classList.toggle('is-selected', isSelected);
            el.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        });
    }

    function syncDisabled(container, select) {
        const trigger = container.querySelector('.custom-select-trigger');
        if (!trigger) return;
        if (select.disabled) {
            trigger.classList.add('is-disabled');
            trigger.setAttribute('aria-disabled', 'true');
        } else {
            trigger.classList.remove('is-disabled');
            trigger.removeAttribute('aria-disabled');
        }
    }

    /** Handle key events on the trigger */
    function handleKeydown(event, container, trigger, panel, select) {
        const count = panel.children.length;
        if (count === 0) return;

        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                trigger.blur();
                const next = currentHighlightedIndex(panel) + 1;
                scrollToOption(panel, Math.min(next, count - 1));
                break;
            case 'ArrowUp':
                event.preventDefault();
                trigger.blur();
                const prev = currentHighlightedIndex(panel) - 1;
                scrollToOption(panel, Math.max(prev, 0));
                break;
            case 'Enter':
            case ' ':
                event.preventDefault();
                trigger.blur();
                selectHighlighted(panel, select);
                break;
            case 'Home':
                event.preventDefault();
                trigger.blur();
                scrollToOption(panel, 0);
                break;
            case 'End':
                event.preventDefault();
                trigger.blur();
                scrollToOption(panel, count - 1);
                break;
            case 'Escape':
                event.preventDefault();
                closeAllPanels();
                break;
            default:
                // Type-to-jump: filter options by prefix
                if (event.key.length === 1) {
                    typeToJump(event.key, container, panel, select);
                }
                break;
        }
    }

    /** Find the currently highlighted index in the panel */
    function currentHighlightedIndex(panel) {
        return Array.from(panel.children).reduce(function (acc, child, idx) {
            if (child.classList.contains('is-highlighted')) return idx;
            return acc;
        }, -1);
    }

    /** Scroll the highlighted option into view, no-op if none highlighted */
    function scrollToOption(panel, idx) {
        const child = panel.children[idx];
        if (!child) return;
        child.scrollIntoView({ block: 'nearest' });
    }

    /** Highlight the option matching a typed prefix */
    function typeToJump(typedLetter, container, panel, select) {
        const cur = currentHighlightedIndex(panel);
        const children = Array.from(panel.children);
        const filtered = children.filter(function (child) {
            return child.textContent.toLowerCase().startsWith(typedLetter.toLowerCase());
        });

        if (filtered.length > 0) {
            const newIdx = currentHighlightedIndex(panel) + filtered.length > 0
                ? cur + filtered.indexOf(filtered[0])
                : 0;
            highlightItem(panel, Math.min(newIdx, children.length - 1));
            if (newIdx >= 0) {
                event && event.preventDefault && event.preventDefault();
            }
        }
    }

    /** Highlight an option by its DOM index in panel */
    function highlightItem(panel, index) {
        const children = Array.from(panel.children).filter(function (c) { return !c.classList.contains('is-disabled'); });
        panel.querySelectorAll('.custom-select-option').forEach(function (el) {
            el.classList.remove('is-highlighted');
        });

        const target = children[index];
        if (target) {
            target.classList.add('is-highlighted');
            const id = target.id;
            panel.setAttribute('aria-activedescendant', id ? ('opt-' + index) : '');
        }
    }

    /** Select the highlighted option, emit change */
    function selectHighlighted(panel, select) {
        const highlighted = panel.querySelector('.custom-select-option.is-highlighted');
        if (!highlighted) return;
        hiddenSetSelected(select, highlighted.dataset.value);
        updateTrigger(container, select);
        closeAllPanels();
    }

    function hiddenSetSelected(select, value) {
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === value) {
                select.selectedIndex = i;
                select.dispatchEvent(new Event('change'));
                select.dispatchEvent(new Event('input'));
                return;
            }
        }
    }

    function valueOfOption(option) {
        return option.value;
    }

    /** When the hidden select changes, sync everything back to the UI */
    function onValueChange(container, select) {
        updateTrigger(container, select);
        syncDisabled(container, select);
    }

    // Initialize
    enhanceSelects();

    // Watch the entire document for new selects created dynamically
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== Node.ELEMENT_NODE) return;

                // Check if a newly added node contains a select
                if (node.querySelector && node.querySelector('select')) {
                    enhanceSelects();
                }
            });
        });
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
})();
