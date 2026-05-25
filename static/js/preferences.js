/**
 * preferences.js — User Preferences Module for CMS Image Gallery
 *
 * Purpose: Abstract local storage access with fallback mechanisms for persistent user preferences.
 * Requirements: REQ-6 (User Preferences), REQ-9 (Preferences Persistence Service)
 *
 * Features:
 *   - Grid size preference (2, 3, 4, or 5 columns)
 *   - Sort order preference (newest, most_liked, most_viewed)
 *   - localStorage as primary storage with sessionStorage fallback
 *   - In-memory storage as final fallback
 *   - Namespace all keys with "gallery:" prefix to avoid conflicts
 *
 * Requirements Coverage:
 *   - 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9 — Grid size and sort preferences
 *   - 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7 — Storage abstraction with fallbacks
 */

class Preferences {
  /**
   * In-memory storage fallback when both localStorage and sessionStorage are unavailable.
   * @private
   */
  static _memoryStorage = {};

  /**
   * Namespace prefix for all storage keys to avoid conflicts with other applications.
   * @private
   */
  static _namespace = 'gallery:';

  /**
   * Storage strategy detection and fallback chain.
   * Tries localStorage → sessionStorage → in-memory storage.
   * @private
   */
  static _getStorage() {
    // Try localStorage first (Requirement 9.1)
    try {
      if (typeof localStorage !== 'undefined' && localStorage !== null) {
        // Test if localStorage is actually writable (some browsers block it in private mode)
        const testKey = this._namespace + '__test__';
        localStorage.setItem(testKey, 'test');
        localStorage.removeItem(testKey);
        return { type: 'localStorage', storage: localStorage };
      }
    } catch (e) {
      // localStorage unavailable or quota exceeded
    }

    // Fallback to sessionStorage (Requirement 9.5)
    try {
      if (typeof sessionStorage !== 'undefined' && sessionStorage !== null) {
        const testKey = this._namespace + '__test__';
        sessionStorage.setItem(testKey, 'test');
        sessionStorage.removeItem(testKey);
        return { type: 'sessionStorage', storage: sessionStorage };
      }
    } catch (e) {
      // sessionStorage unavailable
    }

    // Final fallback to in-memory storage (Requirement 9.6)
    return { type: 'memory', storage: this._memoryStorage };
  }

  /**
   * Get a preference value from storage.
   * 
   * @param {string} key - The preference key (without namespace prefix)
   * @param {*} defaultValue - Default value to return if key doesn't exist
   * @returns {*} The stored value or defaultValue if not found
   * 
   * Requirements: 9.2, 9.4
   */
  static get(key, defaultValue = null) {
    try {
      const { type, storage } = this._getStorage();
      const namespacedKey = this._namespace + key;

      if (type === 'memory') {
        // In-memory storage: direct access
        return storage[namespacedKey] !== undefined ? storage[namespacedKey] : defaultValue;
      } else {
        // localStorage or sessionStorage: deserialize JSON (Requirement 9.4)
        const value = storage.getItem(namespacedKey);
        if (value === null) {
          return defaultValue;
        }
        return JSON.parse(value);
      }
    } catch (e) {
      console.warn('Preferences.get error:', e);
      return defaultValue;
    }
  }

  /**
   * Set a preference value in storage.
   * 
   * @param {string} key - The preference key (without namespace prefix)
   * @param {*} value - The value to store (will be JSON serialized)
   * @returns {boolean} True if successful, false otherwise
   * 
   * Requirements: 9.2, 9.3
   */
  static set(key, value) {
    try {
      const { type, storage } = this._getStorage();
      const namespacedKey = this._namespace + key;

      if (type === 'memory') {
        // In-memory storage: direct assignment
        storage[namespacedKey] = value;
        return true;
      } else {
        // localStorage or sessionStorage: serialize to JSON (Requirement 9.3)
        storage.setItem(namespacedKey, JSON.stringify(value));
        return true;
      }
    } catch (e) {
      console.warn('Preferences.set error:', e);
      return false;
    }
  }

  /**
   * Remove a preference from storage.
   * 
   * @param {string} key - The preference key (without namespace prefix)
   * @returns {boolean} True if successful, false otherwise
   * 
   * Requirements: 9.2
   */
  static remove(key) {
    try {
      const { type, storage } = this._getStorage();
      const namespacedKey = this._namespace + key;

      if (type === 'memory') {
        delete storage[namespacedKey];
        return true;
      } else {
        storage.removeItem(namespacedKey);
        return true;
      }
    } catch (e) {
      console.warn('Preferences.remove error:', e);
      return false;
    }
  }

  /**
   * Clear all gallery preferences from storage.
   * Only removes keys with the gallery namespace prefix.
   * 
   * @returns {boolean} True if successful, false otherwise
   * 
   * Requirements: 9.2
   */
  static clear() {
    try {
      const { type, storage } = this._getStorage();

      if (type === 'memory') {
        // Clear all namespaced keys from memory storage
        Object.keys(storage).forEach(key => {
          if (key.startsWith(this._namespace)) {
            delete storage[key];
          }
        });
        return true;
      } else {
        // Clear all namespaced keys from localStorage/sessionStorage
        const keysToRemove = [];
        for (let i = 0; i < storage.length; i++) {
          const key = storage.key(i);
          if (key && key.startsWith(this._namespace)) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach(key => storage.removeItem(key));
        return true;
      }
    } catch (e) {
      console.warn('Preferences.clear error:', e);
      return false;
    }
  }

  /* ====================================================================
     Specific Preference Getters and Setters
     ==================================================================== */

  /**
   * Get the grid size preference (number of columns).
   * 
   * @returns {number} Grid size (2, 3, 4, or 5 columns). Default: 4
   * 
   * Requirements: 6.1, 6.4, 6.9
   */
  static getGridSize() {
    const gridSize = this.get('grid_size', 4);
    // Validate grid size is within allowed range
    if ([2, 3, 4, 5].includes(gridSize)) {
      return gridSize;
    }
    return 4; // Default to 4 columns (Requirement 6.9)
  }

  /**
   * Set the grid size preference.
   * 
   * @param {number} columns - Number of columns (2, 3, 4, or 5)
   * @returns {boolean} True if successful, false otherwise
   * 
   * Requirements: 6.2, 6.3
   */
  static setGridSize(columns) {
    // Validate input
    if (![2, 3, 4, 5].includes(columns)) {
      console.warn('Invalid grid size:', columns, '(must be 2, 3, 4, or 5)');
      return false;
    }
    return this.set('grid_size', columns);
  }

  /**
   * Get the sort order preference.
   * 
   * @returns {string} Sort order ("newest", "most_liked", or "most_viewed"). Default: "newest"
   * 
   * Requirements: 6.5, 6.8, 6.9
   */
  static getSortOrder() {
    const sortOrder = this.get('sort_order', 'newest');
    // Validate sort order is one of the allowed values
    if (['newest', 'most_liked', 'most_viewed'].includes(sortOrder)) {
      return sortOrder;
    }
    return 'newest'; // Default to newest (Requirement 6.9)
  }

  /**
   * Set the sort order preference.
   * 
   * @param {string} order - Sort order ("newest", "most_liked", or "most_viewed")
   * @returns {boolean} True if successful, false otherwise
   * 
   * Requirements: 6.6, 6.7
   */
  static setSortOrder(order) {
    // Validate input
    if (!['newest', 'most_liked', 'most_viewed'].includes(order)) {
      console.warn('Invalid sort order:', order, '(must be "newest", "most_liked", or "most_viewed")');
      return false;
    }
    return this.set('sort_order', order);
  }

  /**
   * Get the view mode preference (grid or list).
   * 
   * @returns {string} View mode ("grid" or "list"). Default: "grid"
   */
  static getViewMode() {
    const viewMode = this.get('view_mode', 'grid');
    // Validate view mode is one of the allowed values
    if (['grid', 'list'].includes(viewMode)) {
      return viewMode;
    }
    return 'grid'; // Default to grid view
  }

  /**
   * Set the view mode preference.
   * 
   * @param {string} mode - View mode ("grid" or "list")
   * @returns {boolean} True if successful, false otherwise
   */
  static setViewMode(mode) {
    // Validate input
    if (!['grid', 'list'].includes(mode)) {
      console.warn('Invalid view mode:', mode, '(must be "grid" or "list")');
      return false;
    }
    return this.set('view_mode', mode);
  }

  /**
   * Apply all saved preferences to the gallery on page load.
   * This should be called during initialization to restore user settings.
   * 
   * @returns {Object} Object containing applied preferences
   * 
   * Requirements: 6.4, 6.8
   */
  static applyPreferences() {
    const gridSize = this.getGridSize();
    const sortOrder = this.getSortOrder();
    const viewMode = this.getViewMode();

    return {
      gridSize,
      sortOrder,
      viewMode
    };
  }
}

// Export for use in other modules (if using ES6 modules)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Preferences;
}

// Make available globally for inline scripts
if (typeof window !== 'undefined') {
  window.Preferences = Preferences;
}
