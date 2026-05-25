/**
 * FilterPreview - Real-time image filter preview using HTML5 Canvas
 * 
 * Provides client-side image filtering with instant preview before upload.
 * Supports: grayscale, sepia, brightness, contrast, and saturation adjustments.
 * 
 * Requirements: REQ-3 (Image Filters)
 */

class FilterPreview {
  /**
   * Initialize filter preview with canvas and image file
   * @param {HTMLCanvasElement} canvasElement - Canvas element for rendering
   * @param {File} imageFile - Image file to preview
   */
  constructor(canvasElement, imageFile) {
    this.canvas = canvasElement;
    this.imageFile = imageFile;
    this.disabled = false;
    this.originalImageData = null;
    this.currentImageData = null;
    
    // Filter state
    this.filters = {
      grayscale: false,
      sepia: false,
      brightness: 0,    // -50 to 50
      contrast: 0,      // -50 to 50
      saturation: 0     // -100 to 100
    };
    
    try {
      this.ctx = canvasElement.getContext('2d', { willReadFrequently: true });
      if (!this.ctx) {
        throw new Error('Canvas not supported');
      }
    } catch (error) {
      console.error('Canvas initialization failed:', error);
      this.disabled = true;
      this._showError('Filter preview unavailable');
      return;
    }
    
    this.image = new Image();
    this._loadImage();
  }
  
  /**
   * Load image file into canvas
   * @private
   */
  _loadImage() {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      this.image.onload = () => {
        // Set canvas dimensions to match image
        this.canvas.width = this.image.width;
        this.canvas.height = this.image.height;
        
        // Draw original image
        this.ctx.drawImage(this.image, 0, 0);
        
        // Store original image data
        this.originalImageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
        this.currentImageData = this._cloneImageData(this.originalImageData);
        
        // Trigger initial render event
        this._dispatchEvent('loaded');
      };
      
      this.image.onerror = () => {
        this.disabled = true;
        this._showError('Failed to load image');
      };
      
      this.image.src = e.target.result;
    };
    
    reader.onerror = () => {
      this.disabled = true;
      this._showError('Failed to read image file');
    };
    
    reader.readAsDataURL(this.imageFile);
  }
  
  /**
   * Clone ImageData object
   * @private
   */
  _cloneImageData(imageData) {
    const cloned = this.ctx.createImageData(imageData.width, imageData.height);
    cloned.data.set(imageData.data);
    return cloned;
  }
  
  /**
   * Apply grayscale filter
   */
  applyGrayscale() {
    if (this.disabled) return;
    this.filters.grayscale = true;
    this._applyFilters();
  }
  
  /**
   * Remove grayscale filter
   */
  removeGrayscale() {
    if (this.disabled) return;
    this.filters.grayscale = false;
    this._applyFilters();
  }
  
  /**
   * Apply sepia filter
   */
  applySepia() {
    if (this.disabled) return;
    this.filters.sepia = true;
    this._applyFilters();
  }
  
  /**
   * Remove sepia filter
   */
  removeSepia() {
    if (this.disabled) return;
    this.filters.sepia = false;
    this._applyFilters();
  }
  
  /**
   * Adjust brightness
   * @param {number} percent - Brightness adjustment (-50 to 50)
   */
  adjustBrightness(percent) {
    if (this.disabled) return;
    this.filters.brightness = Math.max(-50, Math.min(50, percent));
    this._applyFilters();
  }
  
  /**
   * Adjust contrast
   * @param {number} percent - Contrast adjustment (-50 to 50)
   */
  adjustContrast(percent) {
    if (this.disabled) return;
    this.filters.contrast = Math.max(-50, Math.min(50, percent));
    this._applyFilters();
  }
  
  /**
   * Adjust saturation
   * @param {number} percent - Saturation adjustment (-100 to 100)
   */
  adjustSaturation(percent) {
    if (this.disabled) return;
    this.filters.saturation = Math.max(-100, Math.min(100, percent));
    this._applyFilters();
  }
  
  /**
   * Reset all filters to original image
   */
  reset() {
    if (this.disabled) return;
    
    this.filters = {
      grayscale: false,
      sepia: false,
      brightness: 0,
      contrast: 0,
      saturation: 0
    };
    
    this._applyFilters();
    this._dispatchEvent('reset');
  }
  
  /**
   * Apply all active filters to the image
   * @private
   */
  _applyFilters() {
    if (this.disabled || !this.originalImageData) return;
    
    const startTime = performance.now();
    
    // Start with original image data
    this.currentImageData = this._cloneImageData(this.originalImageData);
    const pixels = this.currentImageData.data;
    
    // Apply filters in order
    for (let i = 0; i < pixels.length; i += 4) {
      let r = pixels[i];
      let g = pixels[i + 1];
      let b = pixels[i + 2];
      // Alpha channel (i + 3) is preserved
      
      // 1. Grayscale (if enabled)
      if (this.filters.grayscale) {
        const gray = (r + g + b) / 3;
        r = g = b = gray;
      }
      
      // 2. Sepia (if enabled)
      if (this.filters.sepia) {
        const tr = 0.393 * r + 0.769 * g + 0.189 * b;
        const tg = 0.349 * r + 0.686 * g + 0.168 * b;
        const tb = 0.272 * r + 0.534 * g + 0.131 * b;
        r = tr;
        g = tg;
        b = tb;
      }
      
      // 3. Brightness
      if (this.filters.brightness !== 0) {
        const adjustment = (this.filters.brightness / 100) * 255;
        r += adjustment;
        g += adjustment;
        b += adjustment;
      }
      
      // 4. Contrast
      if (this.filters.contrast !== 0) {
        const factor = (259 * (this.filters.contrast + 100)) / (100 * (259 - this.filters.contrast));
        r = factor * (r - 128) + 128;
        g = factor * (g - 128) + 128;
        b = factor * (b - 128) + 128;
      }
      
      // 5. Saturation
      if (this.filters.saturation !== 0) {
        // Convert to HSL, adjust saturation, convert back to RGB
        const hsl = this._rgbToHsl(r, g, b);
        hsl.s = Math.max(0, Math.min(1, hsl.s * (1 + this.filters.saturation / 100)));
        const rgb = this._hslToRgb(hsl.h, hsl.s, hsl.l);
        r = rgb.r;
        g = rgb.g;
        b = rgb.b;
      }
      
      // Clamp values to 0-255 range
      pixels[i] = Math.max(0, Math.min(255, r));
      pixels[i + 1] = Math.max(0, Math.min(255, g));
      pixels[i + 2] = Math.max(0, Math.min(255, b));
    }
    
    // Draw filtered image to canvas
    this.ctx.putImageData(this.currentImageData, 0, 0);
    
    const endTime = performance.now();
    const duration = endTime - startTime;
    
    // Dispatch update event
    this._dispatchEvent('update', { duration });
  }
  
  /**
   * Convert RGB to HSL color space
   * @private
   */
  _rgbToHsl(r, g, b) {
    r /= 255;
    g /= 255;
    b /= 255;
    
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    
    if (max === min) {
      return { h: 0, s: 0, l };
    }
    
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    
    let h;
    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        break;
      case g:
        h = ((b - r) / d + 2) / 6;
        break;
      case b:
        h = ((r - g) / d + 4) / 6;
        break;
    }
    
    return { h, s, l };
  }
  
  /**
   * Convert HSL to RGB color space
   * @private
   */
  _hslToRgb(h, s, l) {
    let r, g, b;
    
    if (s === 0) {
      r = g = b = l;
    } else {
      const hue2rgb = (p, q, t) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1/6) return p + (q - p) * 6 * t;
        if (t < 1/2) return q;
        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
        return p;
      };
      
      const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
      const p = 2 * l - q;
      
      r = hue2rgb(p, q, h + 1/3);
      g = hue2rgb(p, q, h);
      b = hue2rgb(p, q, h - 1/3);
    }
    
    return {
      r: r * 255,
      g: g * 255,
      b: b * 255
    };
  }
  
  /**
   * Get filtered image as Blob for upload
   * @returns {Promise<Blob>} Filtered image blob
   */
  async getFilteredBlob() {
    if (this.disabled) {
      throw new Error('Filter preview is disabled');
    }
    
    return new Promise((resolve, reject) => {
      this.canvas.toBlob((blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error('Failed to create blob from canvas'));
        }
      }, this.imageFile.type || 'image/jpeg', 0.95);
    });
  }
  
  /**
   * Get current filter specification
   * @returns {Object} Filter parameters
   */
  getFilterSpec() {
    return {
      grayscale: this.filters.grayscale,
      sepia: this.filters.sepia,
      brightness: this.filters.brightness,
      contrast: this.filters.contrast,
      saturation: this.filters.saturation
    };
  }
  
  /**
   * Check if any filters are active
   * @returns {boolean} True if any filter is applied
   */
  hasActiveFilters() {
    return this.filters.grayscale ||
           this.filters.sepia ||
           this.filters.brightness !== 0 ||
           this.filters.contrast !== 0 ||
           this.filters.saturation !== 0;
  }
  
  /**
   * Dispatch custom event
   * @private
   */
  _dispatchEvent(eventName, detail = {}) {
    const event = new CustomEvent(`filterpreview:${eventName}`, {
      detail: {
        filters: this.getFilterSpec(),
        ...detail
      }
    });
    this.canvas.dispatchEvent(event);
  }
  
  /**
   * Show error message
   * @private
   */
  _showError(message) {
    console.error('FilterPreview:', message);
    this._dispatchEvent('error', { message });
  }
  
  /**
   * Destroy the filter preview instance
   */
  destroy() {
    if (this.canvas) {
      this.ctx = null;
      this.canvas = null;
    }
    this.image = null;
    this.originalImageData = null;
    this.currentImageData = null;
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FilterPreview;
}
