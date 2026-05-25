/**
 * bulk-operations.js — Multi-select and bulk operations for CMS Image Gallery
 *
 * Features:
 *   - Multi-select mode with checkboxes on image cards
 *   - Bulk delete with confirmation dialog
 *   - Bulk download as ZIP archive
 *   - Keyboard shortcuts (Ctrl+A select all, ESC clear selection)
 *   - Visual feedback for selected images
 *   - Selection counter badge
 *
 * Requirements: REQ-2 (Bulk Operations)
 */

class BulkOperations {
  /**
   * Initialize the bulk operations manager.
   * 
   * @param {HTMLElement} galleryElement - The gallery container element
   */
  constructor(galleryElement) {
    if (!galleryElement) {
      throw new Error('Gallery element is required for BulkOperations');
    }
    
    this.galleryElement = galleryElement;
    this.selectionMode = false;
    this.selectedIds = new Set();
    
    // UI elements (will be created dynamically)
    this.selectButton = null;
    this.actionBar = null;
    this.selectionCounter = null;
    
    // Bind methods to preserve 'this' context
    this.handleKeyboardShortcuts = this.handleKeyboardShortcuts.bind(this);
    this.handleCheckboxChange = this.handleCheckboxChange.bind(this);
    this.handleCardClick = this.handleCardClick.bind(this);
    
    // Initialize UI
    this.createUI();
    this.attachEventListeners();
  }
  
  /**
   * Create the bulk operations UI elements.
   * Adds select button to toolbar and creates floating action bar.
   */
  createUI() {
    // Create select button in the toolbar
    this.createSelectButton();
    
    // Create floating action bar (hidden by default)
    this.createActionBar();
  }
  
  /**
   * Create the "Select" button in the gallery toolbar.
   */
  createSelectButton() {
    // Find the toolbar (search bar container)
    const toolbar = document.querySelector('.container.mx-auto.px-4.py-6');
    if (!toolbar) {
      console.warn('Toolbar not found for bulk operations select button');
      return;
    }
    
    // Create select button
    this.selectButton = document.createElement('button');
    this.selectButton.type = 'button';
    this.selectButton.id = 'bulk-select-btn';
    this.selectButton.className = 'px-4 py-2 rounded-xl font-medium transition-all duration-200 ' +
      'bg-gradient-to-r from-teal-600 to-teal-700 text-white ' +
      'hover:from-teal-700 hover:to-teal-800 ' +
      'focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 ' +
      'dark:focus:ring-offset-gray-900';
    this.selectButton.innerHTML = '☑️ Select';
    this.selectButton.title = 'Enter selection mode';
    
    // Add to toolbar (after search button)
    const searchBtn = document.getElementById('search-btn');
    if (searchBtn && searchBtn.parentNode) {
      searchBtn.parentNode.insertBefore(this.selectButton, searchBtn.nextSibling);
    } else {
      toolbar.appendChild(this.selectButton);
    }
    
    // Add click handler
    this.selectButton.addEventListener('click', () => {
      if (this.selectionMode) {
        this.exitSelectionMode();
      } else {
        this.enterSelectionMode();
      }
    });
  }
  
  /**
   * Create the floating action bar with bulk action buttons.
   */
  createActionBar() {
    this.actionBar = document.createElement('div');
    this.actionBar.id = 'bulk-action-bar';
    this.actionBar.className = 'fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50 ' +
      'hidden opacity-0 transition-all duration-300 ' +
      'bg-white dark:bg-gray-800 rounded-2xl shadow-2xl ' +
      'border border-gray-200 dark:border-gray-700 ' +
      'px-6 py-4 flex items-center gap-4';
    
    // Selection counter
    this.selectionCounter = document.createElement('span');
    this.selectionCounter.className = 'text-sm font-semibold text-gray-700 dark:text-gray-300';
    this.selectionCounter.textContent = '0 selected';
    
    // Bulk delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.id = 'bulk-delete-btn';
    deleteBtn.className = 'px-4 py-2 rounded-xl font-medium transition-all duration-200 ' +
      'bg-gradient-to-r from-red-500 to-red-600 text-white ' +
      'hover:from-red-600 hover:to-red-700 ' +
      'focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 ' +
      'disabled:opacity-50 disabled:cursor-not-allowed';
    deleteBtn.innerHTML = '🗑️ Delete';
    deleteBtn.title = 'Delete selected images';
    deleteBtn.addEventListener('click', () => this.bulkDelete());
    
    // Bulk download button
    const downloadBtn = document.createElement('button');
    downloadBtn.type = 'button';
    downloadBtn.id = 'bulk-download-btn';
    downloadBtn.className = 'px-4 py-2 rounded-xl font-medium transition-all duration-200 ' +
      'bg-gradient-to-r from-blue-500 to-blue-600 text-white ' +
      'hover:from-blue-600 hover:to-blue-700 ' +
      'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ' +
      'disabled:opacity-50 disabled:cursor-not-allowed';
    downloadBtn.innerHTML = '⬇️ Download';
    downloadBtn.title = 'Download selected images as ZIP';
    downloadBtn.addEventListener('click', () => this.bulkDownload());
    
    // Cancel button
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.id = 'bulk-cancel-btn';
    cancelBtn.className = 'px-4 py-2 rounded-xl font-medium transition-all duration-200 ' +
      'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 ' +
      'hover:bg-gray-300 dark:hover:bg-gray-600 ' +
      'focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2';
    cancelBtn.innerHTML = '✖️ Cancel';
    cancelBtn.title = 'Exit selection mode';
    cancelBtn.addEventListener('click', () => this.exitSelectionMode());
    
    // Assemble action bar
    this.actionBar.appendChild(this.selectionCounter);
    this.actionBar.appendChild(deleteBtn);
    this.actionBar.appendChild(downloadBtn);
    this.actionBar.appendChild(cancelBtn);
    
    // Add to document body
    document.body.appendChild(this.actionBar);
  }
  
  /**
   * Attach event listeners for bulk operations.
   */
  attachEventListeners() {
    // Keyboard shortcuts
    document.addEventListener('keydown', this.handleKeyboardShortcuts);
    
    // Event delegation for checkbox changes
    this.galleryElement.addEventListener('change', this.handleCheckboxChange);
    
    // Event delegation for card clicks in selection mode
    this.galleryElement.addEventListener('click', this.handleCardClick);
  }
  
  /**
   * Handle keyboard shortcuts.
   * - Ctrl+A / Cmd+A: Select all images
   * - ESC: Clear selection and exit selection mode
   * 
   * @param {KeyboardEvent} event - The keyboard event
   */
  handleKeyboardShortcuts(event) {
    // Only handle shortcuts in selection mode
    if (!this.selectionMode) return;
    
    // Ctrl+A or Cmd+A: Select all
    if ((event.ctrlKey || event.metaKey) && event.key === 'a') {
      event.preventDefault();
      this.selectAll();
    }
    
    // ESC: Clear selection and exit selection mode
    if (event.key === 'Escape') {
      event.preventDefault();
      this.exitSelectionMode();
    }
  }
  
  /**
   * Handle checkbox change events.
   * 
   * @param {Event} event - The change event
   */
  handleCheckboxChange(event) {
    const checkbox = event.target;
    if (!checkbox.classList.contains('bulk-select-checkbox')) return;
    
    const imageId = parseInt(checkbox.dataset.imageId, 10);
    if (isNaN(imageId)) return;
    
    if (checkbox.checked) {
      this.selectedIds.add(imageId);
    } else {
      this.selectedIds.delete(imageId);
    }
    
    this.updateUI();
  }
  
  /**
   * Handle card clicks in selection mode.
   * Clicking anywhere on the card toggles selection.
   * 
   * @param {Event} event - The click event
   */
  handleCardClick(event) {
    if (!this.selectionMode) return;
    
    // Don't toggle if clicking on interactive elements
    if (event.target.closest('button, a, input')) return;
    
    // Find the image card
    const card = event.target.closest('[id^="image-card-"]');
    if (!card) return;
    
    // Extract image ID from card ID (format: "image-card-123")
    const imageId = parseInt(card.id.replace('image-card-', ''), 10);
    if (isNaN(imageId)) return;
    
    // Toggle selection
    this.toggleSelection(imageId);
  }
  
  /**
   * Enter selection mode.
   * Shows checkboxes on all image cards and displays action bar.
   */
  enterSelectionMode() {
    this.selectionMode = true;
    
    // Update select button
    if (this.selectButton) {
      this.selectButton.innerHTML = '✖️ Cancel';
      this.selectButton.title = 'Exit selection mode';
      this.selectButton.classList.remove('from-teal-600', 'to-teal-700', 'hover:from-teal-700', 'hover:to-teal-800');
      this.selectButton.classList.add('from-gray-500', 'to-gray-600', 'hover:from-gray-600', 'hover:to-gray-700');
    }
    
    // Add checkboxes to all image cards
    this.addCheckboxesToCards();
    
    // Show action bar with animation
    if (this.actionBar) {
      this.actionBar.classList.remove('hidden');
      // Trigger reflow for animation
      this.actionBar.offsetHeight;
      this.actionBar.classList.add('opacity-100');
      this.actionBar.style.transform = 'translate(-50%, 0)';
    }
    
    // Add visual indicator to gallery
    this.galleryElement.classList.add('selection-mode');
    
    this.updateUI();
  }
  
  /**
   * Exit selection mode.
   * Hides checkboxes and action bar, clears selection.
   */
  exitSelectionMode() {
    this.selectionMode = false;
    
    // Update select button
    if (this.selectButton) {
      this.selectButton.innerHTML = '☑️ Select';
      this.selectButton.title = 'Enter selection mode';
      this.selectButton.classList.remove('from-gray-500', 'to-gray-600', 'hover:from-gray-600', 'hover:to-gray-700');
      this.selectButton.classList.add('from-teal-600', 'to-teal-700', 'hover:from-teal-700', 'hover:to-teal-800');
    }
    
    // Remove checkboxes from all image cards
    this.removeCheckboxesFromCards();
    
    // Hide action bar with animation
    if (this.actionBar) {
      this.actionBar.classList.remove('opacity-100');
      this.actionBar.style.transform = 'translate(-50%, 20px)';
      setTimeout(() => {
        this.actionBar.classList.add('hidden');
      }, 300);
    }
    
    // Remove visual indicator from gallery
    this.galleryElement.classList.remove('selection-mode');
    
    // Clear selection
    this.clearSelection();
  }
  
  /**
   * Check if currently in selection mode.
   * 
   * @returns {boolean} True if in selection mode
   */
  isSelectionMode() {
    return this.selectionMode;
  }
  
  /**
   * Add checkboxes to all image cards.
   */
  addCheckboxesToCards() {
    const cards = this.galleryElement.querySelectorAll('[id^="image-card-"]');
    
    cards.forEach(card => {
      // Extract image ID from card ID
      const imageId = parseInt(card.id.replace('image-card-', ''), 10);
      if (isNaN(imageId)) return;
      
      // Check if checkbox already exists
      if (card.querySelector('.bulk-select-checkbox')) return;
      
      // Create checkbox container
      const checkboxContainer = document.createElement('div');
      checkboxContainer.className = 'bulk-checkbox-container absolute top-3 left-3 z-10';
      
      // Create checkbox
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'bulk-select-checkbox w-6 h-6 rounded-lg cursor-pointer ' +
        'bg-white dark:bg-gray-700 border-2 border-gray-300 dark:border-gray-600 ' +
        'checked:bg-teal-600 checked:border-teal-600 ' +
        'focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 ' +
        'transition-all duration-200';
      checkbox.dataset.imageId = imageId;
      checkbox.checked = this.selectedIds.has(imageId);
      
      checkboxContainer.appendChild(checkbox);
      
      // Add to card (make card position relative if not already)
      const imageContainer = card.querySelector('.image-container');
      if (imageContainer) {
        imageContainer.style.position = 'relative';
        imageContainer.appendChild(checkboxContainer);
      }
      
      // Add selection visual feedback
      if (this.selectedIds.has(imageId)) {
        card.classList.add('bulk-selected');
      }
    });
  }
  
  /**
   * Remove checkboxes from all image cards.
   */
  removeCheckboxesFromCards() {
    const checkboxContainers = this.galleryElement.querySelectorAll('.bulk-checkbox-container');
    checkboxContainers.forEach(container => container.remove());
    
    // Remove selection visual feedback
    const cards = this.galleryElement.querySelectorAll('.bulk-selected');
    cards.forEach(card => card.classList.remove('bulk-selected'));
  }
  
  /**
   * Toggle selection state of an image.
   * 
   * @param {number} imageId - The image ID to toggle
   */
  toggleSelection(imageId) {
    if (this.selectedIds.has(imageId)) {
      this.selectedIds.delete(imageId);
    } else {
      this.selectedIds.add(imageId);
    }
    
    // Update checkbox state
    const checkbox = this.galleryElement.querySelector(
      `.bulk-select-checkbox[data-image-id="${imageId}"]`
    );
    if (checkbox) {
      checkbox.checked = this.selectedIds.has(imageId);
    }
    
    // Update visual feedback
    const card = document.getElementById(`image-card-${imageId}`);
    if (card) {
      if (this.selectedIds.has(imageId)) {
        card.classList.add('bulk-selected');
      } else {
        card.classList.remove('bulk-selected');
      }
    }
    
    this.updateUI();
  }
  
  /**
   * Select all images in the gallery.
   */
  selectAll() {
    const cards = this.galleryElement.querySelectorAll('[id^="image-card-"]');
    
    cards.forEach(card => {
      const imageId = parseInt(card.id.replace('image-card-', ''), 10);
      if (!isNaN(imageId)) {
        this.selectedIds.add(imageId);
        
        // Update checkbox
        const checkbox = card.querySelector('.bulk-select-checkbox');
        if (checkbox) {
          checkbox.checked = true;
        }
        
        // Add visual feedback
        card.classList.add('bulk-selected');
      }
    });
    
    this.updateUI();
  }
  
  /**
   * Clear all selections.
   */
  clearSelection() {
    this.selectedIds.clear();
    
    // Update all checkboxes
    const checkboxes = this.galleryElement.querySelectorAll('.bulk-select-checkbox');
    checkboxes.forEach(checkbox => {
      checkbox.checked = false;
    });
    
    // Remove visual feedback
    const cards = this.galleryElement.querySelectorAll('.bulk-selected');
    cards.forEach(card => card.classList.remove('bulk-selected'));
    
    this.updateUI();
  }
  
  /**
   * Get array of selected image IDs.
   * 
   * @returns {number[]} Array of selected image IDs
   */
  getSelectedIds() {
    return Array.from(this.selectedIds);
  }
  
  /**
   * Update UI elements based on current selection state.
   */
  updateUI() {
    const count = this.selectedIds.size;
    
    // Update selection counter
    if (this.selectionCounter) {
      this.selectionCounter.textContent = `${count} selected`;
    }
    
    // Enable/disable action buttons based on selection count
    const deleteBtn = document.getElementById('bulk-delete-btn');
    const downloadBtn = document.getElementById('bulk-download-btn');
    
    if (deleteBtn) {
      deleteBtn.disabled = count === 0;
    }
    if (downloadBtn) {
      downloadBtn.disabled = count === 0;
    }
  }
  
  /**
   * Perform bulk delete operation.
   * Shows confirmation dialog before deleting.
   */
  async bulkDelete() {
    const selectedIds = this.getSelectedIds();
    
    if (selectedIds.length === 0) {
      this.showToast('No images selected', 'error');
      return;
    }
    
    // Show confirmation dialog
    const confirmed = confirm(
      `Are you sure you want to delete ${selectedIds.length} image${selectedIds.length > 1 ? 's' : ''}? This action cannot be undone.`
    );
    
    if (!confirmed) return;
    
    try {
      // Show loading state
      this.showToast('Deleting images...', 'info');
      
      // Call bulk delete API
      const response = await fetch('/api/bulk-delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ image_ids: selectedIds }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Bulk delete failed');
      }
      
      const data = await response.json();
      
      if (data.success) {
        // Remove deleted cards from DOM
        selectedIds.forEach(imageId => {
          const card = document.getElementById(`image-card-${imageId}`);
          if (card) {
            card.style.transition = 'opacity 0.3s, transform 0.3s';
            card.style.opacity = '0';
            card.style.transform = 'scale(0.95)';
            setTimeout(() => card.remove(), 300);
          }
        });
        
        // Clear selection and exit selection mode
        this.clearSelection();
        this.exitSelectionMode();
        
        // Show success message
        this.showToast(data.message || `Deleted ${selectedIds.length} images`, 'success');
      } else {
        throw new Error(data.error || 'Bulk delete failed');
      }
    } catch (error) {
      console.error('Bulk delete error:', error);
      this.showToast(`Delete failed: ${error.message}`, 'error');
    }
  }
  
  /**
   * Perform bulk download operation.
   * Downloads selected images as a ZIP archive.
   */
  async bulkDownload() {
    const selectedIds = this.getSelectedIds();
    
    if (selectedIds.length === 0) {
      this.showToast('No images selected', 'error');
      return;
    }
    
    try {
      // Show loading state
      this.showToast('Preparing download...', 'info');
      
      // Call bulk download API
      const response = await fetch('/api/bulk-download', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ image_ids: selectedIds }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Bulk download failed');
      }
      
      // Get the ZIP file as a blob
      const blob = await response.blob();
      
      // Create a download link and trigger it
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `images_${Date.now()}.zip`;
      document.body.appendChild(a);
      a.click();
      
      // Cleanup
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      // Show success message
      this.showToast(`Downloaded ${selectedIds.length} images`, 'success');
    } catch (error) {
      console.error('Bulk download error:', error);
      this.showToast(`Download failed: ${error.message}`, 'error');
    }
  }
  
  /**
   * Show a toast notification.
   * Uses the existing toast system from gallery.js if available.
   * 
   * @param {string} message - The message to display
   * @param {string} type - The toast type ('success', 'error', 'info')
   */
  showToast(message, type = 'info') {
    // Use global showToast if available
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
      return;
    }
    
    // Fallback: create simple toast
    const toast = document.createElement('div');
    toast.className = 'fixed top-24 right-4 z-50 px-6 py-3 rounded-xl shadow-lg text-white text-sm font-medium ' +
      'transform transition-all duration-300 translate-x-0 opacity-100';
    
    if (type === 'success') {
      toast.style.background = 'linear-gradient(135deg, #0f5c4e, #0f8c68)';
    } else if (type === 'error') {
      toast.style.background = 'linear-gradient(135deg, #ea6c1a, #c2540e)';
    } else {
      toast.style.background = 'linear-gradient(135deg, #6b7280, #4b5563)';
    }
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Slide out after 3 seconds
    setTimeout(() => {
      toast.style.transform = 'translateX(400px)';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
  
  /**
   * Destroy the bulk operations manager.
   * Removes event listeners and UI elements.
   */
  destroy() {
    // Remove event listeners
    document.removeEventListener('keydown', this.handleKeyboardShortcuts);
    this.galleryElement.removeEventListener('change', this.handleCheckboxChange);
    this.galleryElement.removeEventListener('click', this.handleCardClick);
    
    // Remove UI elements
    if (this.selectButton) {
      this.selectButton.remove();
    }
    if (this.actionBar) {
      this.actionBar.remove();
    }
    
    // Clear selection
    this.clearSelection();
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BulkOperations;
}

// Make available globally
window.BulkOperations = BulkOperations;
