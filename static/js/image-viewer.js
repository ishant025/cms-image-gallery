/**
 * image-viewer.js — Advanced Image Viewer for Lightbox
 * 
 * Provides zoom, pan, and rotate capabilities for the lightbox modal.
 * Supports keyboard shortcuts, mouse wheel, touch gestures, and smooth animations.
 * 
 * Requirements: REQ-1 (Advanced Image Viewer)
 * - 1.1: Display image at fit-to-screen size
 * - 1.2: Zoom between 100% and 400% scale
 * - 1.3: Pan while zoomed
 * - 1.4: Rotate 90 degrees clockwise
 * - 1.5: Reset to original state
 * - 1.6: Preserve zoom/pan when rotating
 * - 1.7: Reset transformations on close
 */

class ImageViewer {
  /**
   * Create an ImageViewer instance
   * @param {HTMLImageElement} imageElement - The image element to control
   * @param {HTMLElement} containerElement - The container element (for bounds checking)
   */
  constructor(imageElement, containerElement) {
    this.image = imageElement;
    this.container = containerElement;
    
    // Transformation state
    this.state = {
      scale: 1.0,        // Current zoom level (1.0 to 4.0)
      translateX: 0,     // Pan offset X in pixels
      translateY: 0,     // Pan offset Y in pixels
      rotation: 0        // Rotation in degrees (0, 90, 180, 270)
    };
    
    // Interaction state
    this.isDragging = false;
    this.dragStart = { x: 0, y: 0 };
    this.lastTranslate = { x: 0, y: 0 };
    
    // Touch gesture state
    this.touchState = {
      initialDistance: 0,
      initialScale: 1.0,
      isPinching: false
    };
    
    // Mobile gesture state (Requirement 8.10, 8.11)
    this.mobileState = {
      lastTapTime: 0,
      doubleTapDelay: 300,  // ms
      controlsVisible: true
    };
    
    // Bind event handlers
    this.boundHandlers = {
      wheel: this.onWheel.bind(this),
      mousedown: this.onMouseDown.bind(this),
      mousemove: this.onMouseMove.bind(this),
      mouseup: this.onMouseUp.bind(this),
      touchstart: this.onTouchStart.bind(this),
      touchmove: this.onTouchMove.bind(this),
      touchend: this.onTouchEnd.bind(this),
      click: this.onClick.bind(this)
    };
    
    // Initialize
    this.attachEventListeners();
    this.applyTransform();
  }
  
  /**
   * Attach all event listeners
   */
  attachEventListeners() {
    // Mouse events
    this.image.addEventListener('wheel', this.boundHandlers.wheel, { passive: false });
    this.image.addEventListener('mousedown', this.boundHandlers.mousedown);
    document.addEventListener('mousemove', this.boundHandlers.mousemove);
    document.addEventListener('mouseup', this.boundHandlers.mouseup);
    
    // Touch events
    this.image.addEventListener('touchstart', this.boundHandlers.touchstart, { passive: false });
    this.image.addEventListener('touchmove', this.boundHandlers.touchmove, { passive: false });
    this.image.addEventListener('touchend', this.boundHandlers.touchend);
    
    // Click event for mobile tap to toggle controls (Requirement 8.10)
    this.image.addEventListener('click', this.boundHandlers.click);
    
    // Prevent default drag behavior
    this.image.style.userSelect = 'none';
    this.image.style.webkitUserSelect = 'none';
    this.image.draggable = false;
  }
  
  /**
   * Remove all event listeners
   */
  detachEventListeners() {
    this.image.removeEventListener('wheel', this.boundHandlers.wheel);
    this.image.removeEventListener('mousedown', this.boundHandlers.mousedown);
    document.removeEventListener('mousemove', this.boundHandlers.mousemove);
    document.removeEventListener('mouseup', this.boundHandlers.mouseup);
    
    this.image.removeEventListener('touchstart', this.boundHandlers.touchstart);
    this.image.removeEventListener('touchmove', this.boundHandlers.touchmove);
    this.image.removeEventListener('touchend', this.boundHandlers.touchend);
    
    this.image.removeEventListener('click', this.boundHandlers.click);
  }
  
  /**
   * Zoom in or out by a delta amount
   * @param {number} delta - Zoom delta (-1 to 1, negative zooms out)
   * @param {number} centerX - X coordinate to zoom towards (optional)
   * @param {number} centerY - Y coordinate to zoom towards (optional)
   */
  zoom(delta, centerX = null, centerY = null) {
    const oldScale = this.state.scale;
    
    // Calculate new scale (0.1 increment per delta unit)
    let newScale = this.state.scale + (delta * 0.1);
    
    // Clamp between 1.0 and 4.0 (Requirement 1.2)
    newScale = Math.max(1.0, Math.min(4.0, newScale));
    
    // If zooming to a specific point, adjust translation to keep that point centered
    if (centerX !== null && centerY !== null && newScale !== oldScale) {
      const rect = this.image.getBoundingClientRect();
      const offsetX = centerX - rect.left - rect.width / 2;
      const offsetY = centerY - rect.top - rect.height / 2;
      
      const scaleRatio = newScale / oldScale;
      this.state.translateX = this.state.translateX * scaleRatio + offsetX * (1 - scaleRatio);
      this.state.translateY = this.state.translateY * scaleRatio + offsetY * (1 - scaleRatio);
    }
    
    this.state.scale = newScale;
    this.applyTransform();
  }
  
  /**
   * Pan the image by pixel offsets
   * @param {number} deltaX - Horizontal pan offset in pixels
   * @param {number} deltaY - Vertical pan offset in pixels
   */
  pan(deltaX, deltaY) {
    // Only allow panning when zoomed (Requirement 1.3)
    if (this.state.scale <= 1.0) return;
    
    this.state.translateX += deltaX;
    this.state.translateY += deltaY;
    
    // Apply bounds checking to prevent panning too far
    this.constrainPan();
    
    this.applyTransform();
  }
  
  /**
   * Rotate the image by degrees (90-degree increments)
   * @param {number} degrees - Rotation amount (typically 90)
   */
  rotate(degrees) {
    // Add rotation and normalize to 0-360 range
    this.state.rotation = (this.state.rotation + degrees) % 360;
    if (this.state.rotation < 0) this.state.rotation += 360;
    
    // Preserve zoom and pan state (Requirement 1.6)
    this.applyTransform();
  }
  
  /**
   * Reset all transformations to original state
   */
  reset() {
    this.state.scale = 1.0;
    this.state.translateX = 0;
    this.state.translateY = 0;
    this.state.rotation = 0;
    this.applyTransform();
  }
  
  /**
   * Apply current transformation state to the image element
   */
  applyTransform() {
    const { scale, translateX, translateY, rotation } = this.state;
    
    // Build CSS transform string
    const transform = `translate(${translateX}px, ${translateY}px) scale(${scale}) rotate(${rotation}deg)`;
    
    this.image.style.transform = transform;
    this.image.style.transition = 'transform 0.2s ease-out';
    
    // Update cursor based on zoom level
    if (scale > 1.0) {
      this.image.style.cursor = this.isDragging ? 'grabbing' : 'grab';
    } else {
      this.image.style.cursor = 'default';
    }
    
    // Show/hide pan instructions based on zoom level
    const panInstructions = document.getElementById('pan-instructions');
    if (panInstructions) {
      if (scale > 1.0) {
        panInstructions.classList.remove('hidden');
        // Trigger reflow to enable transition
        panInstructions.offsetHeight;
        panInstructions.style.opacity = '1';
        
        // Auto-hide after 3 seconds
        clearTimeout(this._panInstructionsTimeout);
        this._panInstructionsTimeout = setTimeout(() => {
          panInstructions.style.opacity = '0';
          setTimeout(() => {
            if (this.state.scale > 1.0) {
              panInstructions.classList.add('hidden');
            }
          }, 300);
        }, 3000);
      } else {
        panInstructions.style.opacity = '0';
        setTimeout(() => {
          panInstructions.classList.add('hidden');
        }, 300);
      }
    }
  }
  
  /**
   * Constrain pan to prevent image from moving too far off screen
   */
  constrainPan() {
    if (this.state.scale <= 1.0) {
      this.state.translateX = 0;
      this.state.translateY = 0;
      return;
    }
    
    const rect = this.image.getBoundingClientRect();
    const containerRect = this.container.getBoundingClientRect();
    
    // Calculate maximum allowed translation
    const maxTranslateX = (rect.width * this.state.scale - rect.width) / 2;
    const maxTranslateY = (rect.height * this.state.scale - rect.height) / 2;
    
    // Constrain translation
    this.state.translateX = Math.max(-maxTranslateX, Math.min(maxTranslateX, this.state.translateX));
    this.state.translateY = Math.max(-maxTranslateY, Math.min(maxTranslateY, this.state.translateY));
  }
  
  /**
   * Mouse wheel event handler for zoom
   * @param {WheelEvent} event
   */
  onWheel(event) {
    event.preventDefault();
    
    // Determine zoom direction from wheel delta
    const delta = event.deltaY > 0 ? -1 : 1;
    
    // Zoom towards mouse position
    this.zoom(delta, event.clientX, event.clientY);
  }
  
  /**
   * Mouse down event handler - start dragging
   * @param {MouseEvent} event
   */
  onMouseDown(event) {
    // Only allow dragging when zoomed
    if (this.state.scale <= 1.0) return;
    
    event.preventDefault();
    this.isDragging = true;
    this.dragStart = { x: event.clientX, y: event.clientY };
    this.lastTranslate = { x: this.state.translateX, y: this.state.translateY };
    
    this.image.style.cursor = 'grabbing';
  }
  
  /**
   * Mouse move event handler - perform dragging
   * @param {MouseEvent} event
   */
  onMouseMove(event) {
    if (!this.isDragging) return;
    
    event.preventDefault();
    
    const deltaX = event.clientX - this.dragStart.x;
    const deltaY = event.clientY - this.dragStart.y;
    
    this.state.translateX = this.lastTranslate.x + deltaX;
    this.state.translateY = this.lastTranslate.y + deltaY;
    
    this.constrainPan();
    this.applyTransform();
  }
  
  /**
   * Mouse up event handler - stop dragging
   * @param {MouseEvent} event
   */
  onMouseUp(event) {
    if (!this.isDragging) return;
    
    this.isDragging = false;
    this.image.style.cursor = this.state.scale > 1.0 ? 'grab' : 'default';
  }
  
  /**
   * Touch start event handler - detect pinch or pan
   * @param {TouchEvent} event
   */
  onTouchStart(event) {
    if (event.touches.length === 2) {
      // Two fingers - pinch zoom
      event.preventDefault();
      this.touchState.isPinching = true;
      this.touchState.initialDistance = this.getTouchDistance(event.touches);
      this.touchState.initialScale = this.state.scale;
    } else if (event.touches.length === 1) {
      // Single touch - check for double tap (Requirement 8.11)
      const currentTime = Date.now();
      const timeSinceLastTap = currentTime - this.mobileState.lastTapTime;
      
      if (timeSinceLastTap < this.mobileState.doubleTapDelay) {
        // Double tap detected - zoom to 200% centered on tap location
        event.preventDefault();
        this.handleDoubleTap(event.touches[0]);
        this.mobileState.lastTapTime = 0; // Reset to prevent triple tap
      } else {
        this.mobileState.lastTapTime = currentTime;
        
        // If zoomed, allow panning
        if (this.state.scale > 1.0) {
          event.preventDefault();
          this.isDragging = true;
          this.dragStart = { 
            x: event.touches[0].clientX, 
            y: event.touches[0].clientY 
          };
          this.lastTranslate = { x: this.state.translateX, y: this.state.translateY };
        }
      }
    }
  }
  
  /**
   * Touch move event handler - perform pinch or pan
   * @param {TouchEvent} event
   */
  onTouchMove(event) {
    if (this.touchState.isPinching && event.touches.length === 2) {
      event.preventDefault();
      
      const currentDistance = this.getTouchDistance(event.touches);
      const scaleChange = currentDistance / this.touchState.initialDistance;
      
      let newScale = this.touchState.initialScale * scaleChange;
      newScale = Math.max(1.0, Math.min(4.0, newScale));
      
      this.state.scale = newScale;
      this.applyTransform();
    } else if (this.isDragging && event.touches.length === 1) {
      event.preventDefault();
      
      const deltaX = event.touches[0].clientX - this.dragStart.x;
      const deltaY = event.touches[0].clientY - this.dragStart.y;
      
      this.state.translateX = this.lastTranslate.x + deltaX;
      this.state.translateY = this.lastTranslate.y + deltaY;
      
      this.constrainPan();
      this.applyTransform();
    }
  }
  
  /**
   * Touch end event handler - end pinch or pan
   * @param {TouchEvent} event
   */
  onTouchEnd(event) {
    if (event.touches.length < 2) {
      this.touchState.isPinching = false;
    }
    if (event.touches.length === 0) {
      this.isDragging = false;
    }
  }
  
  /**
   * Calculate distance between two touch points
   * @param {TouchList} touches
   * @returns {number} Distance in pixels
   */
  getTouchDistance(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }
  
  /**
   * Handle double-tap gesture to zoom to 200% (Requirement 8.11)
   * @param {Touch} touch - The touch point
   */
  handleDoubleTap(touch) {
    const targetScale = 2.0; // 200% zoom
    
    if (this.state.scale === 1.0) {
      // Zoom in to 200% centered on tap location
      const rect = this.image.getBoundingClientRect();
      const offsetX = touch.clientX - rect.left - rect.width / 2;
      const offsetY = touch.clientY - rect.top - rect.height / 2;
      
      this.state.scale = targetScale;
      this.state.translateX = -offsetX * (targetScale - 1);
      this.state.translateY = -offsetY * (targetScale - 1);
      
      this.constrainPan();
      this.applyTransform();
    } else {
      // Already zoomed - reset to 100%
      this.reset();
    }
  }
  
  /**
   * Handle single tap/click to toggle controls visibility (Requirement 8.10)
   * @param {MouseEvent|TouchEvent} event
   */
  onClick(event) {
    // Only handle on mobile devices (screen width < 768px)
    if (window.innerWidth >= 768) return;
    
    // Don't toggle if user was dragging
    if (this.isDragging) return;
    
    // Toggle controls visibility
    this.toggleControls();
  }
  
  /**
   * Toggle visibility of lightbox controls (Requirement 8.10)
   */
  toggleControls() {
    this.mobileState.controlsVisible = !this.mobileState.controlsVisible;
    
    // Get all control elements
    const closeBtn = document.getElementById('lightbox-close');
    const viewerControls = document.getElementById('viewer-controls');
    const infoBar = document.querySelector('#lightbox-modal .mt-4');
    
    // Toggle visibility with smooth transition
    const elements = [closeBtn, viewerControls, infoBar].filter(el => el);
    
    elements.forEach(el => {
      if (this.mobileState.controlsVisible) {
        el.style.opacity = '1';
        el.style.pointerEvents = 'auto';
        el.classList.remove('lightbox-controls-hidden');
      } else {
        el.style.opacity = '0';
        el.style.pointerEvents = 'none';
        el.classList.add('lightbox-controls-hidden');
      }
    });
  }
  
  /**
   * Get current zoom level
   * @returns {number} Current scale (1.0 to 4.0)
   */
  getZoomLevel() {
    return this.state.scale;
  }
  
  /**
   * Get current rotation
   * @returns {number} Current rotation in degrees (0, 90, 180, 270)
   */
  getRotation() {
    return this.state.rotation;
  }
  
  /**
   * Cleanup and remove event listeners
   */
  destroy() {
    this.detachEventListeners();
    this.reset();
  }
}

/**
 * Initialize ImageViewer controls for the lightbox
 * This function should be called when the lightbox opens
 */
function initializeImageViewer() {
  const lightboxImage = document.getElementById('lightbox-image');
  const lightboxModal = document.getElementById('lightbox-modal');
  
  if (!lightboxImage || !lightboxModal) {
    console.warn('ImageViewer: Required elements not found');
    return null;
  }
  
  // Create viewer instance
  const viewer = new ImageViewer(lightboxImage, lightboxModal);
  
  // Add control buttons if they don't exist
  addViewerControls(lightboxModal, viewer);
  
  // Add keyboard shortcuts
  setupKeyboardShortcuts(viewer);
  
  return viewer;
}

/**
 * Add viewer control buttons to the lightbox
 * @param {HTMLElement} modal - The lightbox modal element
 * @param {ImageViewer} viewer - The viewer instance
 */
function addViewerControls(modal, viewer) {
  // Check if controls already exist
  if (document.getElementById('viewer-controls')) return;
  
  // Create controls container
  const controls = document.createElement('div');
  controls.id = 'viewer-controls';
  controls.className = 'absolute bottom-20 left-1/2 transform -translate-x-1/2 flex gap-2 bg-black/70 rounded-lg p-2 z-50';
  
  // Control buttons configuration
  const buttons = [
    { id: 'zoom-in', label: '➕', title: 'Zoom In (+)', action: () => viewer.zoom(1) },
    { id: 'zoom-out', label: '➖', title: 'Zoom Out (-)', action: () => viewer.zoom(-1) },
    { id: 'rotate', label: '🔄', title: 'Rotate (R)', action: () => viewer.rotate(90) },
    { id: 'reset', label: '⟲', title: 'Reset (0)', action: () => viewer.reset() }
  ];
  
  // Create buttons
  buttons.forEach(btn => {
    const button = document.createElement('button');
    button.id = btn.id;
    button.type = 'button';
    button.className = 'px-4 py-2 text-white hover:bg-white/20 rounded transition-colors duration-200 text-lg';
    button.textContent = btn.label;
    button.title = btn.title;
    button.addEventListener('click', (e) => {
      e.stopPropagation();
      btn.action();
    });
    controls.appendChild(button);
  });
  
  // Add zoom level indicator
  const zoomIndicator = document.createElement('div');
  zoomIndicator.id = 'zoom-indicator';
  zoomIndicator.className = 'px-3 py-2 text-white text-sm flex items-center';
  zoomIndicator.textContent = '100%';
  controls.appendChild(zoomIndicator);
  
  // Update zoom indicator when zooming
  const originalApplyTransform = viewer.applyTransform.bind(viewer);
  viewer.applyTransform = function() {
    originalApplyTransform();
    const zoomPercent = Math.round(this.state.scale * 100);
    zoomIndicator.textContent = `${zoomPercent}%`;
  };
  
  modal.appendChild(controls);
}

/**
 * Setup keyboard shortcuts for the viewer
 * @param {ImageViewer} viewer - The viewer instance
 */
function setupKeyboardShortcuts(viewer) {
  const keyHandler = (event) => {
    const lightboxModal = document.getElementById('lightbox-modal');
    
    // Only handle shortcuts when lightbox is open
    if (!lightboxModal || lightboxModal.classList.contains('hidden')) return;
    
    switch(event.key) {
      case '+':
      case '=':
        event.preventDefault();
        viewer.zoom(1);
        break;
      case '-':
      case '_':
        event.preventDefault();
        viewer.zoom(-1);
        break;
      case 'r':
      case 'R':
        event.preventDefault();
        viewer.rotate(90);
        break;
      case '0':
        event.preventDefault();
        viewer.reset();
        break;
      case 'ArrowLeft':
        event.preventDefault();
        // Could be used for navigation between images
        break;
      case 'ArrowRight':
        event.preventDefault();
        // Could be used for navigation between images
        break;
    }
  };
  
  // Store handler reference for cleanup
  if (!window._imageViewerKeyHandler) {
    window._imageViewerKeyHandler = keyHandler;
    document.addEventListener('keydown', keyHandler);
  }
}

/**
 * Cleanup keyboard shortcuts
 */
function cleanupKeyboardShortcuts() {
  if (window._imageViewerKeyHandler) {
    document.removeEventListener('keydown', window._imageViewerKeyHandler);
    window._imageViewerKeyHandler = null;
  }
}

/**
 * Enhanced openLightbox function that initializes the viewer
 * This extends the existing openLightbox function from gallery.js
 */
(function() {
  // Store reference to current viewer instance
  let currentViewer = null;
  
  // Store original openLightbox function
  const originalOpenLightbox = window.openLightbox;
  
  // Override openLightbox to initialize viewer
  window.openLightbox = function(imageId, imageUrl, username, imageIdForView) {
    // Call original function
    if (originalOpenLightbox) {
      originalOpenLightbox(imageId, imageUrl, username, imageIdForView);
    }
    
    // Initialize viewer after a short delay to ensure image is loaded
    setTimeout(() => {
      // Cleanup previous viewer if exists
      if (currentViewer) {
        currentViewer.destroy();
      }
      
      // Create new viewer instance
      currentViewer = initializeImageViewer();
    }, 100);
  };
  
  // Store original closeLightbox function
  const originalCloseLightbox = window.closeLightbox;
  
  // Override closeLightbox to cleanup viewer
  window.closeLightbox = function() {
    // Cleanup viewer (Requirement 1.7)
    if (currentViewer) {
      currentViewer.destroy();
      currentViewer = null;
    }
    
    // Remove controls
    const controls = document.getElementById('viewer-controls');
    if (controls) {
      controls.remove();
    }
    
    // Call original function
    if (originalCloseLightbox) {
      originalCloseLightbox();
    }
  };
})();

// Export for use in other modules if needed
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ImageViewer, initializeImageViewer };
}
