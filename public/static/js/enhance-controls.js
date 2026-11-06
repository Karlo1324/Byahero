/**
 * Custom Form Controls Enhancement
 * Replaces native controls with styled components
 * Preserves all form functionality
 */

document.addEventListener('DOMContentLoaded', () => {
  console.log('[CustomControls] DOM ready, enhancing controls...');
  console.log('[CustomControls] Found', document.querySelectorAll('select').length, 'selects');
  enhanceAllControls();
  console.log('[CustomControls] Enhancement complete');
});

/**
 * Enhance all custom form controls
 */
function enhanceAllControls() {
  // Custom Selects
  document.querySelectorAll('select:not([data-enhanced])').forEach(select => {
    enhanceSelect(select);
  });

  // Custom Date Inputs
  document.querySelectorAll('input[type="date"]:not([data-enhanced])').forEach(input => {
    enhanceDatePicker(input);
  });

  // Custom Time Inputs
  document.querySelectorAll('input[type="time"]:not([data-enhanced])').forEach(input => {
    enhanceTimePicker(input);
  });
}

/**
 * Enhance native select with custom dropdown
 */
function enhanceSelect(select) {
  console.log('[CustomControls] Enhancing select:', select.id || select.name);
  console.log('[CustomControls] Select has', select.options.length, 'options');

  if (select.dataset.enhanced) {
    console.log('[CustomControls] Already enhanced, skipping');
    return;
  }
  select.dataset.enhanced = 'true';

  const id = select.id || 'select-' + Math.random().toString(36).slice(2);
  const optionId = 'option-' + id;

  // Get selected value text
  const getValueText = () => {
    const selected = select.options[select.selectedIndex];
    return selected ? selected.text : 'Select an option';
  };

  // Create wrapper
  const wrapper = document.createElement('div');
  wrapper.className = 'custom-select';
  wrapper.innerHTML = `
    <button type="button"
            class="custom-select-trigger"
            id="${id}"
            aria-haspopup="listbox"
            aria-expanded="false"
            ${select.disabled ? 'disabled' : ''}>
      <span class="custom-select-value">${getValueText()}</span>
      <svg class="custom-select-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </button>
    <div class="custom-select-options"
         role="listbox"
         id="${optionId}"
         aria-labelledby="${id}"
         hidden>
      <div class="custom-select-scroll"></div>
    </div>
  `;

  console.log('[CustomControls] Wrapper created, inserting...');
  // Hide original select but keep it in DOM for form submission
  select.style.position = 'absolute';
  select.style.opacity = '0';
  select.style.pointerEvents = 'none';
  select.style.width = '0';
  select.style.height = '0';

  wrapper.insertBefore(select, wrapper.firstChild);
  select.parentNode.insertBefore(wrapper, select.nextSibling);
  console.log('[CustomControls] Wrapper inserted into DOM');

  const trigger = wrapper.querySelector('.custom-select-trigger');
  const optionsContainer = wrapper.querySelector('.custom-select-options');
  const scrollContainer = wrapper.querySelector('.custom-select-scroll');

  /** Rebuild dropdown options from native select */
  const rebuildOptions = () => {
    console.log('[CustomControls] Rebuilding options, select has', select.options.length, 'options');
    scrollContainer.innerHTML = Array.from(select.options).map(opt =>
      `<div class="custom-select-option ${opt.selected ? 'selected' : ''} ${opt.disabled ? 'disabled' : ''}"
            role="option"
            data-value="${opt.value}"
            aria-selected="${opt.selected}">
        ${opt.textContent}
      </div>`
    ).join('');

    // Rebind click events
    scrollContainer.querySelectorAll('.custom-select-option:not(.disabled)').forEach(option => {
      option.addEventListener('click', selectOption);
    });

    // Update value display if no selection
    const hasSelection = Array.from(select.options).some(o => o.selected);
    if (!hasSelection) {
      wrapper.querySelector('.custom-select-value').textContent = 'Select an option';
    }
  };

  /** Handle option selection */
  const selectOption = (value) => {
    // Update native select
    const option = select.querySelector(`option[value="${value}"]`);
    if (option) {
      option.selected = true;
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Update display
    wrapper.querySelector('.custom-select-value').textContent = option ? option.textContent : getValueText();

    // Update selected state
    scrollContainer.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.toggle('selected', opt.dataset.value === value);
      opt.setAttribute('aria-selected', opt.dataset.value === value ? 'true' : 'false');
    });
  };

  // Initial build
  rebuildOptions();

  // Bind click events to options
  scrollContainer.querySelectorAll('.custom-select-option:not(.disabled)').forEach(option => {
    option.addEventListener('click', () => selectOption(option.dataset.value));
  });

  // Watch for DOM changes to native select (for dynamically added options)
  const observer = new MutationObserver((mutations) => {
    console.log('[CustomControls] Mutation detected on', select.id || select.name);
    let needsRebuild = false;
    mutations.forEach(mutation => {
      if (mutation.type === 'childList' || mutation.type === 'attributes') {
        needsRebuild = true;
      }
    });
    if (needsRebuild) {
      console.log('[CustomControls] Rebuilding options due to mutation');
      rebuildOptions();
      // Re-bind click events after rebuild
      scrollContainer.querySelectorAll('.custom-select-option:not(.disabled)').forEach(option => {
        option.addEventListener('click', () => selectOption(option.dataset.value));
      });
    }
  });

  observer.observe(select, { childList: true, attributes: true, subtree: true });
  console.log('[CustomControls] Observer attached');

  // Toggle dropdown
  const toggleDropdown = () => {
    if (select.disabled) return;
    const isExpanded = trigger.getAttribute('aria-expanded') === 'true';
    trigger.setAttribute('aria-expanded', String(!isExpanded));
    optionsContainer.hidden = !isExpanded;

    // Close other dropdowns
    document.querySelectorAll('.custom-select.is-open').forEach(el => {
      if (el !== wrapper) {
        el.classList.remove('is-open');
        el.querySelector('.custom-select-trigger').setAttribute('aria-expanded', 'false');
        el.querySelector('.custom-select-options').hidden = true;
      }
    });

    wrapper.classList.toggle('is-open', !isExpanded);
  };

  trigger.addEventListener('click', toggleDropdown);

  // Keyboard navigation
  trigger.addEventListener('keydown', (e) => {
    const options = Array.from(wrapper.querySelectorAll('.custom-select-option:not(.disabled)'));
    const current = options.findIndex(opt => opt.classList.contains('selected'));

    if (!options.length) return;

    switch(e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (trigger.getAttribute('aria-expanded') !== 'true') {
          toggleDropdown();
        }
        const next = current < options.length - 1 ? current + 1 : 0;
        options[next].focus();
        break;

      case 'ArrowUp':
        e.preventDefault();
        const prev = current > 0 ? current - 1 : options.length - 1;
        options[prev].focus();
        break;

      case 'Enter':
      case ' ':
        e.preventDefault();
        if (trigger.getAttribute('aria-expanded') === 'true') {
          options[current]?.click();
        } else {
          toggleDropdown();
        }
        break;

      case 'Escape':
        e.preventDefault();
        if (trigger.getAttribute('aria-expanded') === 'true') {
          toggleDropdown();
        }
        break;
    }
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) {
      wrapper.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      optionsContainer.hidden = true;
    }
  });
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
      <span class="custom-date-value">${formatDate(input.value)}</span>
    </div>
  `;

  // Move input into wrapper but hide it
  input.style.position = 'absolute';
  input.style.opacity = '0';
  input.style.pointerEvents = 'none';
  wrapper.appendChild(input);

  input.parentNode.insertBefore(wrapper, input.nextSibling);

  // Click to focus native picker
  wrapper.querySelector('.custom-date-display').addEventListener('click', () => {
    input.showPicker?.();
    input.focus();
  });

  // Update display on change
  const updateDisplay = () => {
    wrapper.querySelector('.custom-date-value').textContent = formatDate(input.value);
  };

  input.addEventListener('change', updateDisplay);
  input.addEventListener('input', updateDisplay);
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
      <span class="custom-time-value">${input.value || 'Select time'}</span>
    </div>
  `;

  input.style.position = 'absolute';
  input.style.opacity = '0';
  input.style.pointerEvents = 'none';
  wrapper.appendChild(input);

  input.parentNode.insertBefore(wrapper, input.nextSibling);

  wrapper.querySelector('.custom-time-display').addEventListener('click', () => {
    input.showPicker?.();
    input.focus();
  });
}

/**
 * Format date for display
 */
function formatDate(dateStr) {
  if (!dateStr) return 'Select date';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  } catch {
    return dateStr;
  }
}

/**
 * Re-enhance controls after AJAX content loads
 */
window.enhanceControls = enhanceAllControls;
