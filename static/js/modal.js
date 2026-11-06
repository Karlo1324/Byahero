/**
 * ByaHero Modal System
 * Reusable modal/result popup system for all pages
 */

(function() {
  'use strict';

  // Modal template
  const MODAL_TEMPLATE = `
    <div class="modal-overlay" id="modalOverlay" onclick="ByaHeroModal.close()">
      <div class="modal-card" onclick="event.stopPropagation()">
        <div class="modal-header">
          <h3 id="modalTitle">Title</h3>
          <button class="modal-close" onclick="ByaHeroModal.close()">&times;</button>
        </div>
        <div class="modal-body" id="modalBody"></div>
        <div class="modal-footer" id="modalFooter"></div>
      </div>
    </div>
  `;

  let overlay = null;

  function ensureModal() {
    if (!overlay) {
      document.body.insertAdjacentHTML('beforeend', MODAL_TEMPLATE);
      overlay = document.getElementById('modalOverlay');
    }
    return overlay;
  }

  window.ByaHeroModal = {
    /**
     * Open a modal with custom content
     * @param {Object} options
     *   - title: string
     *   - html: string (content for modal body)
     *   - footer: string (optional, for buttons)
     *   - className: string (additional class for modal-card)
     *   - onClose: function (optional callback)
     */
    open: function(options) {
      const o = options || {};
      const modal = ensureModal();

      modal.querySelector('#modalTitle').textContent = o.title || '';
      modal.querySelector('#modalBody').innerHTML = o.html || '';
      modal.querySelector('#modalFooter').innerHTML = o.footer || '';
      modal.querySelector('.modal-card').className = 'modal-card ' + (o.className || '');

      modal._onClose = o.onClose || null;

      // Trigger reflow for animation
      modal.offsetHeight;
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';

      // Focus trap
      const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusable) focusable.focus();
    },

    /**
     * Close the modal
     */
    close: function() {
      const modal = document.getElementById('modalOverlay');
      if (!modal) return;

      modal.classList.remove('open');
      document.body.style.overflow = '';

      if (modal._onClose) {
        modal._onClose();
        modal._onClose = null;
      }
    },

    /**
     * Show a toast notification
     * @param {string} message
     * @param {'success'|'error'|'info'} type
     * @param {number} duration ms
     */
    toast: function(message, type = 'info', duration = 3000) {
      const existing = document.querySelector('.toast');
      if (existing) existing.remove();

      const toast = document.createElement('div');
      toast.className = 'toast ' + type;
      toast.textContent = message;
      document.body.appendChild(toast);

      // Trigger animation
      toast.offsetHeight;
      toast.classList.add('show');

      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }, duration);
    },

    /**
     * Show a success result modal (for trip planner, add arrival, etc.)
     * @param {Object} data
     */
    showResult: function(data) {
      const html = data.html || '<p>Done</p>';
      const footer = data.footer || '';
      this.open({
        title: data.title || 'Result',
        html: html,
        footer: footer,
        className: 'result-modal',
        onClose: data.onClose
      });
    },

    /**
     * Show a confirmation dialog
     * @param {Object} options
     *   - title: string
     *   - message: string
     *   - confirmText: string
     *   - cancelText: string
     *   - onConfirm: function
     *   - onCancel: function (optional)
     */
    confirm: function(options) {
      const o = options || {};
      const footer = `
        <button class="btn btn-secondary" onclick="ByaHeroModal._confirmCancel()">${o.cancelText || 'Cancel'}</button>
        <button class="btn btn-primary" onclick="ByaHeroModal._confirmOk()">${o.confirmText || 'OK'}</button>
      `;

      this.open({
        title: o.title || 'Confirm',
        html: `<p>${o.message}</p>`,
        footer: footer,
        onClose: o.onCancel
      });

      this._confirmOk = function() {
        this.close();
        if (o.onConfirm) o.onConfirm();
        this._confirmOk = this._confirmCancel = null;
      };

      this._confirmCancel = function() {
        this.close();
        if (o.onCancel) o.onCancel();
        this._confirmOk = this._confirmCancel = null;
      };
    }
  };

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('modalOverlay');
      if (modal && modal.classList.contains('open')) {
        ByaHeroModal.close();
      }
    }
  });

  // Expose globally
  window.ByaHeroModal = window.ByaHeroModal;
})();