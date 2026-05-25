/**
 * progressive-loading.js — Progressive Image Loading with Blur-Up Effect
 *
 * Implements blur-up effect using Intersection Observer for lazy loading.
 * Images load with low-resolution thumbnails first (blurred), then transition
 * to full-resolution images smoothly when they enter the viewport.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.5, 4.7
 * - REQ-4.1: Display low-resolution placeholder images immediately
 * - REQ-4.2: Show blurred version while high-resolution loads
 * - REQ-4.3: Transition from blur to sharp within 300ms
 * - REQ-4.5: Use CSS blur filter with 20px radius
 * - REQ-4.7: Prioritize images in viewport before off-screen images
 */

class ProgressiveLoader {
  /**
   * Initialize the progressive loader with Intersection Observer.
   * 
   * @param {HTMLElement} containerElement - The container element holding images
   */
  constructor(containerElement) {
    this.container = containerElement;
    this.observer = null;
    
    // Initialize Intersection Observer if supported
    if ('IntersectionObserver' in window) {
      this.initObserver();
    } else {
      // Fallback: load all images immediately if IntersectionObserver not supported
      console.warn('IntersectionObserver not supported, loading all images immediately');
      this.loadAllImages();
    }
  }

  /**
   * Initialize the Intersection Observer to watch for images entering viewport.
   * Requirement 4.7: Prioritize images in viewport before off-screen images
   */
  initObserver() {
    const options = {
      root: null, // Use viewport as root
      rootMargin: '50px', // Start loading 50px before entering viewport
      threshold: 0.01 // Trigger when even 1% of image is visible
    };

    this.observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const imageElement = entry.target;
          this.loadImage(imageElement);
          this.observer.unobserve(imageElement); // Stop observing once loaded
        }
      });
    }, options);

    // Observe all progressive images in the container
    this.observeAllImages();
  }

  /**
   * Find and observe all progressive images in the container.
   */
  observeAllImages() {
    if (!this.container) return;

    const images = this.container.querySelectorAll('.progressive-image');
    images.forEach(img => this.observe(img));
  }

  /**
   * Start observing an image element for viewport entry.
   * Requirement 4.7: Prioritize images in viewport
   * 
   * @param {HTMLElement} imageElement - The image element to observe
   */
  observe(imageElement) {
    if (!this.observer || !imageElement) return;
    
    // Check if image already has full-resolution src
    if (imageElement.classList.contains('loaded')) return;
    
    this.observer.observe(imageElement);
  }

  /**
   * Stop observing an image element.
   * 
   * @param {HTMLElement} imageElement - The image element to unobserve
   */
  unobserve(imageElement) {
    if (!this.observer || !imageElement) return;
    this.observer.unobserve(imageElement);
  }

  /**
   * Load the full-resolution image and transition from blur to sharp.
   * Requirements 4.2, 4.3, 4.5:
   * - Show blurred version while loading
   * - Transition from blur to sharp within 300ms
   * - Use CSS blur filter with 20px radius
   * 
   * @param {HTMLElement} imageElement - The image element to load
   */
  loadImage(imageElement) {
    if (!imageElement) return;

    // Get the full-resolution URL from data attribute
    const fullUrl = imageElement.getAttribute('data-full-url');
    if (!fullUrl) {
      console.warn('No data-full-url attribute found on image', imageElement);
      return;
    }

    // Skip if already loaded
    if (imageElement.classList.contains('loaded')) return;

    // Create a new image object to preload the full-resolution image
    const fullImage = new Image();

    // Set up load handler
    fullImage.onload = () => {
      // Swap to full-resolution image
      imageElement.src = fullUrl;
      
      // Remove blur effect with CSS transition (300ms)
      // Requirement 4.3: Transition within 300ms
      imageElement.classList.add('loaded');
      
      // Clean up
      fullImage.onload = null;
      fullImage.onerror = null;
    };

    // Set up error handler
    // Requirement 4.6: Display error placeholder with retry option
    fullImage.onerror = () => {
      console.error('Failed to load image:', fullUrl);
      
      // Add error class for styling
      imageElement.classList.add('load-error');
      
      // Optionally show retry button or error indicator
      this.showErrorPlaceholder(imageElement, fullUrl);
      
      // Clean up
      fullImage.onload = null;
      fullImage.onerror = null;
    };

    // Start loading the full-resolution image
    fullImage.src = fullUrl;
  }

  /**
   * Show an error placeholder when image fails to load.
   * Requirement 4.6: Display error placeholder with retry option
   * 
   * @param {HTMLElement} imageElement - The image element that failed to load
   * @param {string} fullUrl - The URL that failed to load
   */
  showErrorPlaceholder(imageElement, fullUrl) {
    // Remove blur effect
    imageElement.classList.add('loaded');
    
    // Create error overlay
    const errorOverlay = document.createElement('div');
    errorOverlay.className = 'progressive-image-error';
    errorOverlay.innerHTML = `
      <div class="error-content">
        <span class="error-icon">⚠️</span>
        <span class="error-text">Failed to load image</span>
        <button class="retry-btn" data-retry-url="${fullUrl}">Retry</button>
      </div>
    `;
    
    // Insert error overlay after the image
    imageElement.parentNode.insertBefore(errorOverlay, imageElement.nextSibling);
    
    // Add retry handler
    const retryBtn = errorOverlay.querySelector('.retry-btn');
    if (retryBtn) {
      retryBtn.addEventListener('click', () => {
        // Remove error overlay
        errorOverlay.remove();
        
        // Remove error class
        imageElement.classList.remove('load-error');
        imageElement.classList.remove('loaded');
        
        // Retry loading
        this.loadImage(imageElement);
      });
    }
  }

  /**
   * Fallback method to load all images immediately (for browsers without IntersectionObserver).
   */
  loadAllImages() {
    if (!this.container) return;

    const images = this.container.querySelectorAll('.progressive-image');
    images.forEach(img => this.loadImage(img));
  }

  /**
   * Disconnect the observer and clean up.
   */
  disconnect() {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
  }

  /**
   * Refresh the observer to watch for new images added to the DOM.
   * Useful after dynamic content updates (e.g., search results, infinite scroll).
   */
  refresh() {
    if (this.observer) {
      this.observeAllImages();
    }
  }
}

/**
 * Initialize progressive loading on page load.
 * Requirement 4.1: Display low-resolution placeholder images immediately
 */
function initProgressiveLoading() {
  const galleryContainer = document.getElementById('gallery-grid');
  
  if (!galleryContainer) {
    console.warn('Gallery container not found, progressive loading not initialized');
    return null;
  }

  return new ProgressiveLoader(galleryContainer);
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ProgressiveLoader, initProgressiveLoading };
}

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initProgressiveLoading);
} else {
  // DOM already loaded
  initProgressiveLoading();
}
