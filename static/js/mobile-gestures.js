/**
 * mobile-gestures.js — Mobile Gesture Handler for CMS Image Gallery
 *
 * Purpose: Detect and handle touch gestures for mobile interactions.
 * Requirements: REQ-8 (Mobile Experience), REQ-15 (Mobile Gesture Handler)
 *
 * Features:
 *   - Swipe left/right for image navigation and action reveals
 *   - Pull-to-refresh for gallery reload
 *   - Long press for image options menu
 *   - Double tap for zoom in lightbox
 *   - Touch-friendly target sizes (44x44px minimum)
 *   - Prevent default browser gestures where appropriate
 *
 * Requirements Coverage:
 *   - 8.4, 8.5 — Swipe left/right on image cards
 *   - 8.6, 8.7, 8.8 — Pull-to-refresh functionality
 *   - 8.9 — Touch target sizes (44x44px minimum)
 *   - 8.11 — Double-tap to zoom in lightbox
 *   - 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8 — Gesture detection
 */

class MobileGestures {
  /**
   * Create a MobileGestures instance
   * @param {HTMLElement} element - The element to attach gesture listeners to
   * @param {Object} options - Configuration options
   */
  constructor(element, options = {}) {
    this.element = element;
    
    // Configuration with defaults
    this.config = {
      swipeThreshold: options.swipeThreshold || 50,      // Minimum distance for swipe (Requirement 15.1)
      pullThreshold: options.pullThreshold || 80,        // Minimum distance for pull (Requirement 15.2)
      longPressDelay: options.longPressDelay || 500,     // Long press duration in ms
      doubleTapDelay: options.doubleTapDelay || 300,     // Max time between taps for double-tap
      velocityThreshold: options.velocityThreshold || 0.3 // Minimum velocity for swipe
    };
    
    // Touch state tracking
    this.touchState = {
      startX: 0,
      startY: 0,
      currentX: 0,
      currentY: 0,
      startTime: 0,
      endTime: 0,
      isTracking: false,
      isPulling: false,
      lastTapTime: 0,
      longPressTimer: null
    };
    
    // Callback registry
    this.callbacks = {
      swipeLeft: [],
      swipeRight: [],
      pullDown: [],
      doubleTap: [],
      longPress: []
    };
    
    // Bind event handlers
    this.boundHandlers = {
      touchstart: this.onTouchStart.bind(this),
      touchmove: this.onTouchMove.bind(this),
      touchend: this.onTouchEnd.bind(this),
      touchcancel: this.onTouchCancel.bind(this)
    };
    
    // Initialize
    this.attachEventListeners();
  }
  
  /**
   * Attach touch event listeners (Requirement 15.5)
   */
  attachEventListeners() {
    this.element.addEventListener('touchstart', this.boundHandlers.touchstart, { passive: false });
    this.element.addEventListener('touchmove', this.boundHandlers.touchmove, { passive: false });
    this.element.addEventListener('touchend', this.boundHandlers.touchend, { passive: false });
    this.element.addEventListener('touchcancel', this.boundHandlers.touchcancel);
  }
  
  /**
   * Remove touch event listeners
   */
  detachEventListeners() {
    this.element.removeEventListener('touchstart', this.boundHandlers.touchstart);
    this.element.removeEventListener('touchmove', this.boundHandlers.touchmove);
    this.element.removeEventListener('touchend', this.boundHandlers.touchend);
    this.element.removeEventListener('touchcancel', this.boundHandlers.touchcancel);
  }
  
  /**
   * Touch start event handler
   * @param {TouchEvent} event
   */
  onTouchStart(event) {
    // Only handle single-touch gestures
    if (event.touches.length !== 1) {
      this.resetTouchState();
      return;
    }
    
    const touch = event.touches[0];
    
    // Record touch start position and time
    this.touchState.startX = touch.clientX;
    this.touchState.startY = touch.clientY;
    this.touchState.currentX = touch.clientX;
    this.touchState.currentY = touch.clientY;
    this.touchState.startTime = Date.now();
    this.touchState.isTracking = true;
    
    // Check for double-tap
    const timeSinceLastTap = this.touchState.startTime - this.touchState.lastTapTime;
    if (timeSinceLastTap < this.config.doubleTapDelay) {
      // Double-tap detected
      this.triggerCallback('doubleTap', {
        x: touch.clientX,
        y: touch.clientY,
        target: event.target
      });
      this.touchState.lastTapTime = 0; // Reset to prevent triple-tap
      this.touchState.isTracking = false;
      return;
    }
    
    // Start long press timer
    this.touchState.longPressTimer = setTimeout(() => {
      if (this.touchState.isTracking) {
        // Check if finger hasn't moved much (within 10px)
        const deltaX = Math.abs(this.touchState.currentX - this.touchState.startX);
        const deltaY = Math.abs(this.touchState.currentY - this.touchState.startY);
        
        if (deltaX < 10 && deltaY < 10) {
          this.triggerCallback('longPress', {
            x: this.touchState.currentX,
            y: this.touchState.currentY,
            target: event.target
          });
          this.touchState.isTracking = false;
        }
      }
    }, this.config.longPressDelay);
  }
  
  /**
   * Touch move event handler
   * @param {TouchEvent} event
   */
  onTouchMove(event) {
    if (!this.touchState.isTracking || event.touches.length !== 1) {
      return;
    }
    
    const touch = event.touches[0];
    this.touchState.currentX = touch.clientX;
    this.touchState.currentY = touch.clientY;
    
    // Calculate deltas
    const deltaX = this.touchState.currentX - this.touchState.startX;
    const deltaY = this.touchState.currentY - this.touchState.startY;
    
    // Determine if this is a horizontal or vertical gesture (Requirement 15.4)
    const absX = Math.abs(deltaX);
    const absY = Math.abs(deltaY);
    
    // Check for pull-down gesture (Requirement 15.2)
    if (deltaY > 0 && absY > absX && absY > this.config.pullThreshold / 2) {
      // Vertical pull detected
      if (!this.touchState.isPulling && this.isAtTop()) {
        this.touchState.isPulling = true;
        // Prevent default scroll behavior (Requirement 15.6)
        event.preventDefault();
      }
      
      if (this.touchState.isPulling) {
        event.preventDefault();
        // Could trigger visual feedback here (e.g., pull indicator)
      }
    }
    
    // Check for horizontal swipe (Requirement 15.1)
    if (absX > absY && absX > this.config.swipeThreshold / 2) {
      // Horizontal swipe detected - prevent default to avoid back/forward navigation
      event.preventDefault();
    }
    
    // Cancel long press if finger moved too much
    if (absX > 10 || absY > 10) {
      this.clearLongPressTimer();
    }
  }
  
  /**
   * Touch end event handler
   * @param {TouchEvent} event
   */
  onTouchEnd(event) {
    if (!this.touchState.isTracking) {
      return;
    }
    
    this.touchState.endTime = Date.now();
    
    // Calculate gesture metrics
    const deltaX = this.touchState.currentX - this.touchState.startX;
    const deltaY = this.touchState.currentY - this.touchState.startY;
    const absX = Math.abs(deltaX);
    const absY = Math.abs(deltaY);
    const duration = this.touchState.endTime - this.touchState.startTime;
    
    // Calculate velocity (Requirement 15.3)
    const velocityX = absX / duration;
    const velocityY = absY / duration;
    
    // Determine gesture type
    if (absX > absY) {
      // Horizontal gesture - check for swipe (Requirement 15.1, 15.4)
      if (absX > this.config.swipeThreshold && velocityX > this.config.velocityThreshold) {
        if (deltaX > 0) {
          // Swipe right
          this.triggerCallback('swipeRight', {
            distance: absX,
            velocity: velocityX,
            duration: duration,
            target: event.target
          });
        } else {
          // Swipe left
          this.triggerCallback('swipeLeft', {
            distance: absX,
            velocity: velocityX,
            duration: duration,
            target: event.target
          });
        }
        
        // Debounce rapid gestures (Requirement 15.8)
        this.touchState.isTracking = false;
      }
    } else {
      // Vertical gesture - check for pull-down (Requirement 15.2)
      if (this.touchState.isPulling && deltaY > this.config.pullThreshold) {
        this.triggerCallback('pullDown', {
          distance: absY,
          velocity: velocityY,
          duration: duration,
          target: event.target
        });
      }
    }
    
    // Record tap time for double-tap detection
    if (absX < 10 && absY < 10 && duration < 200) {
      this.touchState.lastTapTime = this.touchState.endTime;
    }
    
    // Reset state
    this.resetTouchState();
  }
  
  /**
   * Touch cancel event handler
   * @param {TouchEvent} event
   */
  onTouchCancel(event) {
    this.resetTouchState();
  }
  
  /**
   * Reset touch state
   */
  resetTouchState() {
    this.touchState.isTracking = false;
    this.touchState.isPulling = false;
    this.clearLongPressTimer();
  }
  
  /**
   * Clear long press timer
   */
  clearLongPressTimer() {
    if (this.touchState.longPressTimer) {
      clearTimeout(this.touchState.longPressTimer);
      this.touchState.longPressTimer = null;
    }
  }
  
  /**
   * Check if element is scrolled to top (for pull-to-refresh)
   * @returns {boolean}
   */
  isAtTop() {
    // Check if window is at top
    if (window.scrollY > 0) {
      return false;
    }
    
    // Check if element is at top
    if (this.element.scrollTop > 0) {
      return false;
    }
    
    return true;
  }
  
  /**
   * Register a callback for swipe left gesture (Requirement 15.7)
   * @param {Function} callback - Function to call on swipe left
   */
  onSwipeLeft(callback) {
    if (typeof callback === 'function') {
      this.callbacks.swipeLeft.push(callback);
    }
  }
  
  /**
   * Register a callback for swipe right gesture (Requirement 15.7)
   * @param {Function} callback - Function to call on swipe right
   */
  onSwipeRight(callback) {
    if (typeof callback === 'function') {
      this.callbacks.swipeRight.push(callback);
    }
  }
  
  /**
   * Register a callback for pull down gesture (Requirement 15.7)
   * @param {Function} callback - Function to call on pull down
   */
  onPullDown(callback) {
    if (typeof callback === 'function') {
      this.callbacks.pullDown.push(callback);
    }
  }
  
  /**
   * Register a callback for double tap gesture
   * @param {Function} callback - Function to call on double tap
   */
  onDoubleTap(callback) {
    if (typeof callback === 'function') {
      this.callbacks.doubleTap.push(callback);
    }
  }
  
  /**
   * Register a callback for long press gesture
   * @param {Function} callback - Function to call on long press
   */
  onLongPress(callback) {
    if (typeof callback === 'function') {
      this.callbacks.longPress.push(callback);
    }
  }
  
  /**
   * Trigger all callbacks for a gesture type (Requirement 15.8 - debouncing)
   * @param {string} type - Gesture type
   * @param {Object} data - Gesture data to pass to callbacks
   */
  triggerCallback(type, data) {
    if (this.callbacks[type]) {
      this.callbacks[type].forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in ${type} callback:`, error);
        }
      });
    }
  }
  
  /**
   * Set swipe threshold
   * @param {number} pixels - Threshold in pixels
   */
  setSwipeThreshold(pixels) {
    this.config.swipeThreshold = pixels;
  }
  
  /**
   * Set pull threshold
   * @param {number} pixels - Threshold in pixels
   */
  setPullThreshold(pixels) {
    this.config.pullThreshold = pixels;
  }
  
  /**
   * Cleanup and remove event listeners
   */
  destroy() {
    this.detachEventListeners();
    this.resetTouchState();
    this.callbacks = {
      swipeLeft: [],
      swipeRight: [],
      pullDown: [],
      doubleTap: [],
      longPress: []
    };
  }
}

/**
 * Initialize mobile gestures for image cards
 * Implements swipe-to-reveal actions (Requirements 8.4, 8.5)
 */
function initializeImageCardGestures() {
  const galleryGrid = document.getElementById('gallery-grid');
  if (!galleryGrid) return;
  
  // Create gesture handler for the gallery
  const gestureHandler = new MobileGestures(galleryGrid);
  
  // Track which card is currently revealed
  let revealedCard = null;
  
  // Handle swipe left on image cards - reveal actions
  gestureHandler.onSwipeLeft((data) => {
    const imageCard = data.target.closest('[id^="image-card-"]');
    if (!imageCard) return;
    
    // Hide any previously revealed card
    if (revealedCard && revealedCard !== imageCard) {
      hideCardActions(revealedCard);
    }
    
    // Show actions for this card
    showCardActions(imageCard);
    revealedCard = imageCard;
  });
  
  // Handle swipe right - hide actions
  gestureHandler.onSwipeRight((data) => {
    if (revealedCard) {
      hideCardActions(revealedCard);
      revealedCard = null;
    }
  });
  
  // Handle long press - show options menu
  gestureHandler.onLongPress((data) => {
    const imageCard = data.target.closest('[id^="image-card-"]');
    if (!imageCard) return;
    
    // Show context menu or options
    showImageOptions(imageCard, data.x, data.y);
  });
  
  return gestureHandler;
}

/**
 * Show action buttons for an image card
 * @param {HTMLElement} card - The image card element
 */
function showCardActions(card) {
  // Check if actions already exist
  let actionsBar = card.querySelector('.swipe-actions');
  
  if (!actionsBar) {
    // Create actions bar
    actionsBar = document.createElement('div');
    actionsBar.className = 'swipe-actions absolute right-0 top-0 h-full flex items-center gap-2 px-3 bg-gradient-to-l from-red-500 to-orange-500';
    actionsBar.style.transform = 'translateX(100%)';
    actionsBar.style.transition = 'transform 0.3s ease-out';
    
    // Get image ID from card
    const imageId = card.id.replace('image-card-', '');
    
    // Create delete button (44x44px minimum - Requirement 8.9)
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'w-11 h-11 flex items-center justify-center text-white text-xl rounded-full bg-white/20 hover:bg-white/30 transition-colors';
    deleteBtn.innerHTML = '🗑️';
    deleteBtn.title = 'Delete';
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      // Trigger delete action
      const deleteButton = card.querySelector('.delete-btn');
      if (deleteButton) {
        deleteButton.click();
      }
    };
    
    // Create download button (44x44px minimum - Requirement 8.9)
    const downloadBtn = document.createElement('button');
    downloadBtn.type = 'button';
    downloadBtn.className = 'w-11 h-11 flex items-center justify-center text-white text-xl rounded-full bg-white/20 hover:bg-white/30 transition-colors';
    downloadBtn.innerHTML = '⬇️';
    downloadBtn.title = 'Download';
    downloadBtn.onclick = (e) => {
      e.stopPropagation();
      // Trigger download
      window.location.href = `/download/${imageId}`;
    };
    
    actionsBar.appendChild(deleteBtn);
    actionsBar.appendChild(downloadBtn);
    
    // Add to card
    card.style.position = 'relative';
    card.style.overflow = 'hidden';
    card.appendChild(actionsBar);
  }
  
  // Slide in actions
  setTimeout(() => {
    actionsBar.style.transform = 'translateX(0)';
  }, 10);
}

/**
 * Hide action buttons for an image card
 * @param {HTMLElement} card - The image card element
 */
function hideCardActions(card) {
  const actionsBar = card.querySelector('.swipe-actions');
  if (actionsBar) {
    actionsBar.style.transform = 'translateX(100%)';
    setTimeout(() => {
      actionsBar.remove();
    }, 300);
  }
}

/**
 * Show options menu for an image card
 * @param {HTMLElement} card - The image card element
 * @param {number} x - Touch X position
 * @param {number} y - Touch Y position
 */
function showImageOptions(card, x, y) {
  // This could show a context menu with more options
  // For now, just show the swipe actions
  showCardActions(card);
}

/**
 * Initialize pull-to-refresh for gallery
 * Implements pull-to-refresh functionality (Requirements 8.6, 8.7, 8.8)
 */
function initializePullToRefresh() {
  const galleryContainer = document.querySelector('body');
  if (!galleryContainer) return;
  
  // Create gesture handler
  const gestureHandler = new MobileGestures(galleryContainer);
  
  // Create pull indicator
  const pullIndicator = document.createElement('div');
  pullIndicator.id = 'pull-indicator';
  pullIndicator.className = 'fixed top-0 left-1/2 transform -translate-x-1/2 -translate-y-full transition-transform duration-300 z-50';
  pullIndicator.innerHTML = `
    <div class="bg-white dark:bg-gray-800 rounded-full shadow-lg p-3 mt-4">
      <div class="animate-spin w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full"></div>
    </div>
  `;
  document.body.appendChild(pullIndicator);
  
  // Handle pull down gesture
  gestureHandler.onPullDown((data) => {
    // Show loading indicator (Requirement 8.7)
    pullIndicator.style.transform = 'translate(-50%, 0)';
    
    // Reload gallery content (Requirement 8.6)
    setTimeout(() => {
      window.location.reload();
    }, 500);
  });
  
  return gestureHandler;
}

/**
 * Initialize double-tap zoom for lightbox
 * Implements double-tap to zoom (Requirement 8.11)
 */
function initializeLightboxGestures() {
  const lightboxModal = document.getElementById('lightbox-modal');
  const lightboxImage = document.getElementById('lightbox-image');
  
  if (!lightboxModal || !lightboxImage) return;
  
  // Create gesture handler for lightbox
  const gestureHandler = new MobileGestures(lightboxImage);
  
  // Handle double-tap to zoom
  gestureHandler.onDoubleTap((data) => {
    // Check if ImageViewer is available
    if (window.ImageViewer && window.currentImageViewer) {
      const viewer = window.currentImageViewer;
      const currentZoom = viewer.getZoomLevel();
      
      if (currentZoom === 1.0) {
        // Zoom to 200% centered on tap location (Requirement 8.11)
        viewer.zoom(10, data.x, data.y); // 10 * 0.1 = 1.0 zoom increase
      } else {
        // Reset zoom
        viewer.reset();
      }
    }
  });
  
  // Handle tap to toggle controls (Requirement 8.10)
  let lastTapTime = 0;
  gestureHandler.onSwipeLeft(() => {}); // Dummy to enable tap detection
  
  lightboxImage.addEventListener('click', (e) => {
    const now = Date.now();
    if (now - lastTapTime > 300) { // Not a double-tap
      toggleLightboxControls();
    }
    lastTapTime = now;
  });
  
  return gestureHandler;
}

/**
 * Toggle visibility of lightbox controls
 */
function toggleLightboxControls() {
  const controls = document.getElementById('viewer-controls');
  const closeBtn = document.getElementById('lightbox-close');
  const downloadBtn = document.getElementById('lightbox-download');
  const username = document.getElementById('lightbox-username');
  const views = document.getElementById('lightbox-views');
  
  const elements = [controls, closeBtn, downloadBtn, username, views].filter(el => el);
  
  elements.forEach(el => {
    if (el.style.opacity === '0' || el.style.opacity === '') {
      el.style.opacity = '1';
      el.style.pointerEvents = 'auto';
    } else {
      el.style.opacity = '0';
      el.style.pointerEvents = 'none';
    }
  });
}

/**
 * Initialize all mobile gestures on page load
 */
function initializeAllMobileGestures() {
  // Only initialize on mobile devices
  if (window.innerWidth >= 768) {
    return; // Not mobile
  }
  
  // Initialize image card gestures
  const cardGestures = initializeImageCardGestures();
  
  // Initialize pull-to-refresh
  const pullGestures = initializePullToRefresh();
  
  // Initialize lightbox gestures
  const lightboxGestures = initializeLightboxGestures();
  
  // Store gesture handlers for cleanup
  window._mobileGestureHandlers = {
    cardGestures,
    pullGestures,
    lightboxGestures
  };
}

/**
 * Cleanup all mobile gesture handlers
 */
function cleanupMobileGestures() {
  if (window._mobileGestureHandlers) {
    Object.values(window._mobileGestureHandlers).forEach(handler => {
      if (handler && handler.destroy) {
        handler.destroy();
      }
    });
    window._mobileGestureHandlers = null;
  }
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeAllMobileGestures);
} else {
  initializeAllMobileGestures();
}

// Reinitialize on window resize (if crossing mobile/desktop threshold)
let lastWidth = window.innerWidth;
window.addEventListener('resize', () => {
  const currentWidth = window.innerWidth;
  const wasMobile = lastWidth < 768;
  const isMobile = currentWidth < 768;
  
  if (wasMobile !== isMobile) {
    if (isMobile) {
      initializeAllMobileGestures();
    } else {
      cleanupMobileGestures();
    }
  }
  
  lastWidth = currentWidth;
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    MobileGestures,
    initializeImageCardGestures,
    initializePullToRefresh,
    initializeLightboxGestures,
    initializeAllMobileGestures,
    cleanupMobileGestures
  };
}

// Make available globally
if (typeof window !== 'undefined') {
  window.MobileGestures = MobileGestures;
}
