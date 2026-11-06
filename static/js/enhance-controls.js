/**
 * Custom Form Controls Enhancement
 * Replaces native controls with styled components.
 * The native elements stay in the DOM (same id/name/value), so form
 * handling in script.js keeps working unchanged.
 */

(function () {
  'use strict';

  function init() {
    enhanceAllControls();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /**
   * Enhance all custom form controls.
   * Each control is wrapped in try/catch so one failure can never stop the
   * rest of the page from being enhanced.
   */
  function enhanceAllControls() {
    const run = (selector, fn) => {
      document.querySelectorAll(selector).forEach(el => {
        try {
          fn(el);
        } catch (err) {
          console.error('[CustomControls] Failed to enhance', el, err);
        }
      });
    };

    run('select:not([data-enhanced])', enhanceSelect);
    run('input[type="date"]:not([data-enhanced])', enhanceDatePicker);
    run('input[type="time"]:not([data-enhanced])', enhanceTimePicker);
    run('input[type="radio"]:not([data-enhanced])', enhanceRadio);
  }

  /**
   * Enhance native select with a custom dropdown
   */
  function enhanceSelect(select) {
    if (select.dataset.enhanced) return;
    select.dataset.enhanced = 'true';

    // The select KEEPS its id: script.js uses getElementById('route') etc.
    const baseId = select.id || 'select-' + Math.random().toString(36).slice(2);
    const triggerId = 'trigger-' + baseId;
    const listId = 'option-' + baseId;

    const getValueText = () => {
      const selected = select.options[select.selectedIndex];
      return selected && selected.text ? selected.text : 'Select an option';
    };

    // Build wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select';
    wrapper.innerHTML = `
      <button type="button"
              class="custom-select-trigger"
              id="${triggerId}"
              aria-haspopup="listbox"
              aria-expanded="false"
              aria-controls="${listId}">
        <span class="custom-select-value"></span>
        <svg class="custom-select-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
      <div class="custom-select-options"
           role="listbox"
           id="${listId}"
           aria-labelledby="${triggerId}"
           hidden>
        <div class="custom-select-scroll"></div>
      </div>
    `;

    // Hide the native select but keep it in the DOM for form submission
    select.style.position = 'absolute';
    select.style.opacity = '0';
    select.style.pointerEvents = 'none';
    select.style.width = '0';
    select.style.height = '0';
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    // IMPORTANT ORDER: put the wrapper where the select is FIRST,
    // then move the select inside it.
    // (Moving the select first made select.nextSibling point inside the
    // wrapper, so insertBefore threw and the dropdown vanished.)
    select.parentNode.insertBefore(wrapper, select);
    wrapper.insertBefore(select, wrapper.firstChild);

    const trigger = wrapper.querySelector('.custom-select-trigger');
    const valueEl = wrapper.querySelector('.custom-select-value');
    const optionsContainer = wrapper.querySelector('.custom-select-options');
    const scrollContainer = wrapper.querySelector('.custom-select-scroll');

    /** Open / close helpers */
    const closeDropdown = () => {
      wrapper.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      optionsContainer.hidden = true;
    };

    const openDropdown = () => {
      if (select.disabled) return;

      // Close any other open dropdowns
      document.querySelectorAll('.custom-select.is-open').forEach(el => {
        if (el !== wrapper) {
          el.classList.remove('is-open');
          el.querySelector('.custom-select-trigger').setAttribute('aria-expanded', 'false');
          el.querySelector('.custom-select-options').hidden = true;
        }
      });

      wrapper.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      optionsContainer.hidden = false;

      const selected = scrollContainer.querySelector('.custom-select-option.selected');
      if (selected && selected.scrollIntoView) {
        selected.scrollIntoView({ block: 'nearest' });
      }
    };

    const isOpen = () => trigger.getAttribute('aria-expanded') === 'true';
    const toggleDropdown = () => (isOpen() ? closeDropdown() : openDropdown());

    /** Sync the custom UI from the native select's current state */
    const syncFromSelect = () => {
      valueEl.textContent = getValueText();
      trigger.disabled = select.disabled;
      if (select.disabled) closeDropdown();

      scrollContainer.querySelectorAll('.custom-select-option').forEach(opt => {
        const on = opt.dataset.value === select.value && !!select.value;
        opt.classList.toggle('selected', on);
        opt.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    };

    /** Choose an option (updates the native select + fires 'change') */
    const selectOption = (value) => {
      const option = Array.from(select.options).find(o => o.value === value);
      if (!option || option.disabled) return;

      select.value = value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      syncFromSelect();
      closeDropdown();
      trigger.focus();
    };

    /** Rebuild the custom option list from the native <option>s */
    const rebuildOptions = () => {
      scrollContainer.innerHTML = '';

      Array.from(select.options).forEach(opt => {
        const div = document.createElement('div');
        div.className = 'custom-select-option' + (opt.disabled ? ' disabled' : '');
        div.setAttribute('role', 'option');
        div.setAttribute('tabindex', '-1');
        div.dataset.value = opt.value;
        div.textContent = opt.textContent; // textContent: no HTML injection

        if (!opt.disabled) {
          div.addEventListener('click', () => selectOption(opt.value));
        }
        scrollContainer.appendChild(div);
      });

      syncFromSelect();
    };

    rebuildOptions();

    // Rebuild when script.js adds/removes options or toggles `disabled`.
    // Batched so adding 20 options one-by-one only rebuilds once.
    let rebuildQueued = false;
    const queueRebuild = () => {
      if (rebuildQueued) return;
      rebuildQueued = true;
      Promise.resolve().then(() => {
        rebuildQueued = false;
        rebuildOptions();
      });
    };

    const observer = new MutationObserver(queueRebuild);
    observer.observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['disabled', 'selected', 'value', 'label']
    });

    // Keep in sync if something else changes the value
    select.addEventListener('change', syncFromSelect);

    // form.reset() doesn't fire 'change', so re-sync after a reset
    if (select.form) {
      select.form.addEventListener('reset', () => setTimeout(syncFromSelect, 0));
    }

    // Clicking <label for="route"> should focus the custom trigger
    if (select.id) {
      document.querySelectorAll(`label[for="${select.id}"]`).forEach(label => {
        label.addEventListener('click', (e) => {
          e.preventDefault();
          if (!select.disabled) trigger.focus();
        });
      });
    }

    // Toggle on click
    trigger.addEventListener('click', toggleDropdown);

    // Keyboard navigation (works from the trigger and from focused options)
    wrapper.addEventListener('keydown', (e) => {
      const options = Array.from(
        scrollContainer.querySelectorAll('.custom-select-option:not(.disabled)')
      );
      if (!options.length && e.key !== 'Escape') return;

      const active = document.activeElement;
      let index = options.indexOf(active);
      if (index === -1) index = options.findIndex(o => o.classList.contains('selected'));

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          if (!isOpen()) openDropdown();
          options[index < options.length - 1 ? index + 1 : 0].focus();
          break;

        case 'ArrowUp':
          e.preventDefault();
          if (!isOpen()) openDropdown();
          options[index > 0 ? index - 1 : options.length - 1].focus();
          break;

        case 'Enter':
        case ' ':
          if (active && active.classList.contains('custom-select-option')) {
            e.preventDefault();
            selectOption(active.dataset.value);
          } else if (active === trigger) {
            e.preventDefault();
            toggleDropdown();
          }
          break;

        case 'Escape':
          if (isOpen()) {
            e.preventDefault();
            closeDropdown();
            trigger.focus();
          }
          break;

        case 'Tab':
          closeDropdown();
          break;
      }
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!wrapper.contains(e.target)) closeDropdown();
    });
  }

  /**
   * Enhance radio buttons with custom styling
   */
  function enhanceRadio(input) {
    if (input.dataset.enhanced) return;
    input.dataset.enhanced = 'true';

    // Find the label: <label for="id"> or a label wrapping the input
    let label = null;
    if (input.id) {
      label = document.querySelector(`label[for="${input.id}"]`);
    }
    if (!label) label = input.closest('label');
    if (!label) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-radio';

    const indicator = document.createElement('span');
    indicator.className = 'custom-radio-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    label.prepend(indicator);
    label.classList.add('custom-radio-label');

    // Insert the wrapper in the label's place FIRST, then move things in.
    label.parentNode.insertBefore(wrapper, label);

    if (label.contains(input)) {
      // Label wraps the input: just wrap the label
      wrapper.appendChild(label);
    } else {
      wrapper.appendChild(input);
      wrapper.appendChild(label);
    }
  }

  /**
   * Enhance date input with custom styling
   */
  function enhanceDatePicker(input) {
    if (input.dataset.enhanced) return;
    input.dataset.enhanced = 'true';

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-date-input';

    wrapper.innerHTML = `
      <div class="custom-date-display">
        <svg class="custom-date-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
          <line x1="16" y1="2" x2="16" y2="6"></line>
          <line x1="8" y1="2" x2="8" y2="6"></line>
          <line x1="3" y1="10" x2="21" y2="10"></line>
        </svg>
        <span class="custom-date-value"></span>
      </div>
    `;

    const valueEl = wrapper.querySelector('.custom-date-value');
    valueEl.textContent = formatDate(input.value);

    input.style.position = 'absolute';
    input.style.opacity = '0';
    input.style.pointerEvents = 'none';

    // Wrapper goes in first, then the input moves inside it
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    wrapper.querySelector('.custom-date-display').addEventListener('click', () => {
      if (input.showPicker) {
        try { input.showPicker(); } catch (e) { /* ignore */ }
      }
      input.focus();
    });

    const updateDisplay = () => {
      valueEl.textContent = formatDate(input.value);
    };
    input.addEventListener('change', updateDisplay);
    input.addEventListener('input', updateDisplay);

    if (input.form) {
      input.form.addEventListener('reset', () => setTimeout(updateDisplay, 0));
    }
  }

  /**
   * Enhance time input with custom styling
   */
  function enhanceTimePicker(input) {
    if (input.dataset.enhanced) return;
    input.dataset.enhanced = 'true';

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-time-input';

    wrapper.innerHTML = `
      <div class="custom-time-display">
        <svg class="custom-time-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <polyline points="12 6 12 12 16 14"></polyline>
        </svg>
        <span class="custom-time-value"></span>
      </div>
    `;

    const valueEl = wrapper.querySelector('.custom-time-value');
    valueEl.textContent = input.value || 'Select time';

    input.style.position = 'absolute';
    input.style.opacity = '0';
    input.style.pointerEvents = 'none';

    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    wrapper.querySelector('.custom-time-display').addEventListener('click', () => {
      if (input.showPicker) {
        try { input.showPicker(); } catch (e) { /* ignore */ }
      }
      input.focus();
    });

    const updateDisplay = () => {
      valueEl.textContent = input.value || 'Select time';
    };
    input.addEventListener('change', updateDisplay);
    input.addEventListener('input', updateDisplay);

    if (input.form) {
      input.form.addEventListener('reset', () => setTimeout(updateDisplay, 0));
    }
  }

  /**
   * Format a YYYY-MM-DD value for display (parsed as LOCAL date so it never
   * shows the previous day in timezones behind UTC)
   */
  function formatDate(dateStr) {
    if (!dateStr) return 'Select date';
    try {
      const parts = dateStr.split('-').map(Number);
      const date = parts.length === 3
        ? new Date(parts[0], parts[1] - 1, parts[2])
        : new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr;
      return date.toLocaleDateString('en-US', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch (e) {
      return dateStr;
    }
  }

  /**
   * Re-enhance controls after AJAX content loads
   */
  window.enhanceControls = enhanceAllControls;
})();