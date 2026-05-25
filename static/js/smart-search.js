/**
 * smart-search.js — Advanced search module for CMS Image Gallery
 *
 * Provides multi-tag search with additional filters:
 *   - Multiple tags (AND logic)
 *   - Date range picker
 *   - Uploader filter dropdown
 *   - Minimum likes filter
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
 */

class SmartSearch {
  /**
   * Initialize the SmartSearch module
   * @param {HTMLElement} searchFormElement - The advanced search form container
   */
  constructor(searchFormElement) {
    this.form = searchFormElement;
    this.selectedTags = new Set();
    this.filters = {
      dateStart: null,
      dateEnd: null,
      uploader: null,
      minLikes: null
    };
    
    // Cache DOM elements
    this.tagInput = null;
    this.tagSuggestions = null;
    this.selectedTagsContainer = null;
    this.dateStartInput = null;
    this.dateEndInput = null;
    this.uploaderSelect = null;
    this.minLikesInput = null;
    this.minLikesValue = null;
    this.searchButton = null;
    this.clearButton = null;
    this.activeFiltersContainer = null;
    this.resultsContainer = null;
    this.loadingIndicator = null;
    
    this._initializeElements();
    this._attachEventListeners();
  }
  
  /**
   * Initialize and cache DOM element references
   * @private
   */
  _initializeElements() {
    if (!this.form) return;
    
    this.tagInput = this.form.querySelector('#smart-tag-input');
    this.tagSuggestions = this.form.querySelector('#tag-suggestions');
    this.selectedTagsContainer = this.form.querySelector('#selected-tags');
    this.dateStartInput = this.form.querySelector('#date-start');
    this.dateEndInput = this.form.querySelector('#date-end');
    this.uploaderSelect = this.form.querySelector('#uploader-filter');
    this.minLikesInput = this.form.querySelector('#min-likes');
    this.minLikesValue = this.form.querySelector('#min-likes-value');
    this.searchButton = this.form.querySelector('#smart-search-btn');
    this.clearButton = this.form.querySelector('#clear-filters-btn');
    this.activeFiltersContainer = this.form.querySelector('#active-filters');
    this.resultsContainer = document.getElementById('gallery-grid');
    this.loadingIndicator = document.getElementById('skeleton-loader');
  }
  
  /**
   * Attach event listeners to form elements
   * @private
   */
  _attachEventListeners() {
    // Tag input with autocomplete
    if (this.tagInput) {
      this.tagInput.addEventListener('input', this._handleTagInput.bind(this));
      this.tagInput.addEventListener('keydown', this._handleTagKeydown.bind(this));
    }
    
    // Date range inputs
    if (this.dateStartInput) {
      this.dateStartInput.addEventListener('change', this._handleDateChange.bind(this));
    }
    if (this.dateEndInput) {
      this.dateEndInput.addEventListener('change', this._handleDateChange.bind(this));
    }
    
    // Uploader dropdown
    if (this.uploaderSelect) {
      this.uploaderSelect.addEventListener('change', this._handleUploaderChange.bind(this));
    }
    
    // Minimum likes slider
    if (this.minLikesInput) {
      this.minLikesInput.addEventListener('input', this._handleMinLikesChange.bind(this));
    }
    
    // Search button
    if (this.searchButton) {
      this.searchButton.addEventListener('click', this.executeSearch.bind(this));
    }
    
    // Clear filters button
    if (this.clearButton) {
      this.clearButton.addEventListener('click', this.clearFilters.bind(this));
    }
    
    // Click outside to close suggestions
    document.addEventListener('click', (e) => {
      if (this.tagSuggestions && !this.form.contains(e.target)) {
        this.tagSuggestions.classList.add('hidden');
      }
    });
  }
  
  /**
   * Handle tag input for autocomplete
   * @private
   */
  async _handleTagInput(event) {
    const query = event.target.value.trim();
    
    if (query.length < 2) {
      if (this.tagSuggestions) {
        this.tagSuggestions.classList.add('hidden');
      }
      return;
    }
    
    // Fetch tag suggestions from backend
    try {
      const response = await fetch(`/api/tags/autocomplete?q=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error('Failed to fetch tag suggestions');
      
      const suggestions = await response.json();
      this._displayTagSuggestions(suggestions);
    } catch (error) {
      console.error('Tag autocomplete error:', error);
    }
  }
  
  /**
   * Display tag suggestions dropdown
   * @private
   */
  _displayTagSuggestions(suggestions) {
    if (!this.tagSuggestions) return;
    
    // Filter out already selected tags
    const filtered = suggestions.filter(tag => !this.selectedTags.has(tag.name));
    
    if (filtered.length === 0) {
      this.tagSuggestions.classList.add('hidden');
      return;
    }
    
    // Build suggestions HTML
    const html = filtered.map(tag => `
      <div class="tag-suggestion px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer transition-colors"
           data-tag="${this._escapeHtml(tag.name)}">
        <span class="font-medium">#${this._escapeHtml(tag.name)}</span>
        <span class="text-xs text-gray-500 ml-2">(${tag.count} images)</span>
      </div>
    `).join('');
    
    this.tagSuggestions.innerHTML = html;
    this.tagSuggestions.classList.remove('hidden');
    
    // Attach click handlers to suggestions
    this.tagSuggestions.querySelectorAll('.tag-suggestion').forEach(el => {
      el.addEventListener('click', () => {
        const tagName = el.getAttribute('data-tag');
        this.addTag(tagName);
        if (this.tagInput) this.tagInput.value = '';
        this.tagSuggestions.classList.add('hidden');
      });
    });
  }
  
  /**
   * Handle keyboard navigation in tag input
   * @private
   */
  _handleTagKeydown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      const tagName = event.target.value.trim();
      if (tagName) {
        this.addTag(tagName);
        event.target.value = '';
        if (this.tagSuggestions) {
          this.tagSuggestions.classList.add('hidden');
        }
      }
    } else if (event.key === 'Escape') {
      if (this.tagSuggestions) {
        this.tagSuggestions.classList.add('hidden');
      }
    }
  }
  
  /**
   * Add a tag to the selected tags set
   * @param {string} tagName - The tag name to add
   */
  addTag(tagName) {
    const normalized = tagName.toLowerCase().trim();
    if (!normalized || this.selectedTags.has(normalized)) return;
    
    this.selectedTags.add(normalized);
    this._updateSelectedTagsDisplay();
    this._updateActiveFilters();
  }
  
  /**
   * Remove a tag from the selected tags set
   * @param {string} tagName - The tag name to remove
   */
  removeTag(tagName) {
    const normalized = tagName.toLowerCase().trim();
    this.selectedTags.delete(normalized);
    this._updateSelectedTagsDisplay();
    this._updateActiveFilters();
  }
  
  /**
   * Update the visual display of selected tags
   * @private
   */
  _updateSelectedTagsDisplay() {
    if (!this.selectedTagsContainer) return;
    
    if (this.selectedTags.size === 0) {
      this.selectedTagsContainer.innerHTML = '<span class="text-sm text-gray-400">No tags selected</span>';
      return;
    }
    
    const html = Array.from(this.selectedTags).map(tag => `
      <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium
                   bg-teal-100 dark:bg-teal-900 text-teal-800 dark:text-teal-200
                   border border-teal-300 dark:border-teal-700">
        #${this._escapeHtml(tag)}
        <button type="button" 
                class="remove-tag ml-1 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                data-tag="${this._escapeHtml(tag)}"
                aria-label="Remove tag">
          ✕
        </button>
      </span>
    `).join('');
    
    this.selectedTagsContainer.innerHTML = html;
    
    // Attach remove handlers
    this.selectedTagsContainer.querySelectorAll('.remove-tag').forEach(btn => {
      btn.addEventListener('click', () => {
        const tagName = btn.getAttribute('data-tag');
        this.removeTag(tagName);
      });
    });
  }
  
  /**
   * Handle date range change
   * @private
   */
  _handleDateChange() {
    this.filters.dateStart = this.dateStartInput?.value || null;
    this.filters.dateEnd = this.dateEndInput?.value || null;
    this._updateActiveFilters();
  }
  
  /**
   * Handle uploader dropdown change
   * @private
   */
  _handleUploaderChange() {
    this.filters.uploader = this.uploaderSelect?.value || null;
    this._updateActiveFilters();
  }
  
  /**
   * Handle minimum likes slider change
   * @private
   */
  _handleMinLikesChange() {
    const value = parseInt(this.minLikesInput?.value || '0', 10);
    this.filters.minLikes = value > 0 ? value : null;
    
    // Update display value
    if (this.minLikesValue) {
      this.minLikesValue.textContent = value;
    }
    
    this._updateActiveFilters();
  }
  
  /**
   * Update the active filters display
   * @private
   */
  _updateActiveFilters() {
    if (!this.activeFiltersContainer) return;
    
    const filters = [];
    
    // Tags filter
    if (this.selectedTags.size > 0) {
      filters.push({
        label: `Tags: ${Array.from(this.selectedTags).join(', ')}`,
        type: 'tags'
      });
    }
    
    // Date range filter
    if (this.filters.dateStart || this.filters.dateEnd) {
      const start = this.filters.dateStart || 'any';
      const end = this.filters.dateEnd || 'any';
      filters.push({
        label: `Date: ${start} to ${end}`,
        type: 'date'
      });
    }
    
    // Uploader filter
    if (this.filters.uploader) {
      const uploaderName = this.uploaderSelect?.selectedOptions[0]?.textContent || this.filters.uploader;
      filters.push({
        label: `Uploader: ${uploaderName}`,
        type: 'uploader'
      });
    }
    
    // Minimum likes filter
    if (this.filters.minLikes) {
      filters.push({
        label: `Min likes: ${this.filters.minLikes}`,
        type: 'likes'
      });
    }
    
    if (filters.length === 0) {
      this.activeFiltersContainer.innerHTML = '<span class="text-sm text-gray-400">No active filters</span>';
      return;
    }
    
    const html = filters.map(filter => `
      <span class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm
                   bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200
                   border border-blue-300 dark:border-blue-700">
        ${this._escapeHtml(filter.label)}
        <button type="button"
                class="remove-filter hover:text-red-600 dark:hover:text-red-400 transition-colors"
                data-filter-type="${filter.type}"
                aria-label="Remove filter">
          ✕
        </button>
      </span>
    `).join('');
    
    this.activeFiltersContainer.innerHTML = html;
    
    // Attach remove handlers
    this.activeFiltersContainer.querySelectorAll('.remove-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        const filterType = btn.getAttribute('data-filter-type');
        this._removeFilter(filterType);
      });
    });
  }
  
  /**
   * Remove a specific filter
   * @private
   */
  _removeFilter(filterType) {
    switch (filterType) {
      case 'tags':
        this.selectedTags.clear();
        this._updateSelectedTagsDisplay();
        break;
      case 'date':
        this.filters.dateStart = null;
        this.filters.dateEnd = null;
        if (this.dateStartInput) this.dateStartInput.value = '';
        if (this.dateEndInput) this.dateEndInput.value = '';
        break;
      case 'uploader':
        this.filters.uploader = null;
        if (this.uploaderSelect) this.uploaderSelect.value = '';
        break;
      case 'likes':
        this.filters.minLikes = null;
        if (this.minLikesInput) this.minLikesInput.value = '0';
        if (this.minLikesValue) this.minLikesValue.textContent = '0';
        break;
    }
    this._updateActiveFilters();
  }
  
  /**
   * Clear all filters and reset the form
   */
  clearFilters() {
    // Clear tags
    this.selectedTags.clear();
    this._updateSelectedTagsDisplay();
    
    // Clear date range
    this.filters.dateStart = null;
    this.filters.dateEnd = null;
    if (this.dateStartInput) this.dateStartInput.value = '';
    if (this.dateEndInput) this.dateEndInput.value = '';
    
    // Clear uploader
    this.filters.uploader = null;
    if (this.uploaderSelect) this.uploaderSelect.value = '';
    
    // Clear minimum likes
    this.filters.minLikes = null;
    if (this.minLikesInput) this.minLikesInput.value = '0';
    if (this.minLikesValue) this.minLikesValue.textContent = '0';
    
    // Clear tag input
    if (this.tagInput) this.tagInput.value = '';
    
    // Update displays
    this._updateActiveFilters();
    
    // Restore original gallery
    this._restoreOriginalGallery();
  }
  
  /**
   * Build query parameters for the search API
   * @returns {URLSearchParams} Query parameters for the API call
   */
  getQueryParams() {
    const params = new URLSearchParams();
    
    // Add tags (comma-separated for AND logic)
    if (this.selectedTags.size > 0) {
      params.append('tags', Array.from(this.selectedTags).join(','));
    }
    
    // Add date range
    if (this.filters.dateStart) {
      params.append('date_start', this.filters.dateStart);
    }
    if (this.filters.dateEnd) {
      params.append('date_end', this.filters.dateEnd);
    }
    
    // Add uploader
    if (this.filters.uploader) {
      params.append('uploader_id', this.filters.uploader);
    }
    
    // Add minimum likes
    if (this.filters.minLikes) {
      params.append('min_likes', this.filters.minLikes);
    }
    
    return params;
  }
  
  /**
   * Execute the advanced search
   */
  async executeSearch() {
    // Validate that at least one filter is set
    if (this.selectedTags.size === 0 && 
        !this.filters.dateStart && 
        !this.filters.dateEnd && 
        !this.filters.uploader && 
        !this.filters.minLikes) {
      this._showToast('Please select at least one filter', 'info');
      return;
    }
    
    // Show loading state
    this._showLoading();
    
    try {
      // Build query parameters
      const params = this.getQueryParams();
      
      // Call the advanced search API
      const response = await fetch(`/api/search-advanced?${params.toString()}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Search request failed');
      }
      
      const data = await response.json();
      
      // Hide loading state
      this._hideLoading();
      
      // Display results
      this._displayResults(data.results || []);
      
      // Show result count
      const count = data.count || 0;
      this._showToast(`Found ${count} image${count !== 1 ? 's' : ''}`, 'success');
      
    } catch (error) {
      console.error('Search error:', error);
      this._hideLoading();
      this._showToast(error.message || 'Search failed. Please try again.', 'error');
    }
  }
  
  /**
   * Display search results in the gallery
   * @private
   */
  _displayResults(results) {
    if (!this.resultsContainer) return;
    
    const noResults = document.getElementById('no-results');
    
    if (results.length === 0) {
      // Show no results message
      this.resultsContainer.innerHTML = '';
      if (noResults) {
        noResults.classList.remove('hidden');
      }
      return;
    }
    
    // Hide no results message
    if (noResults) {
      noResults.classList.add('hidden');
    }
    
    // Render result cards (reuse existing renderCard function from gallery.js)
    const masonryHTML = `
      <div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-4">
        ${results.map(image => this._renderCard(image)).join('')}
      </div>
    `;
    
    this.resultsContainer.innerHTML = masonryHTML;
  }
  
  /**
   * Render a single image card
   * @private
   */
  _renderCard(image) {
    // Build tag badges HTML
    let tagsHTML = '';
    if (image.tag_data && image.tag_data.length > 0) {
      const badgeItems = image.tag_data.map(tagInfo => {
        const isAI = tagInfo.is_ai;
        const confidence = tagInfo.confidence;
        const tagName = tagInfo.name;
        
        const bgColor = isAI ? '#e8f4ff' : '#f0faf7';
        const textColor = isAI ? '#0066cc' : '#0f5c4e';
        const borderColor = isAI ? '#99ccff' : '#a1e0cc';
        const hoverBg = isAI ? '#0066cc' : '#0f5c4e';
        const emoji = isAI ? '🤖' : '';
        const confidenceText = isAI && confidence ? ` <span style="opacity:0.7; font-size:0.85em;">(${Math.round(confidence)}%)</span>` : '';
        const title = isAI ? `AI-generated (${Math.round(confidence)}% confidence)` : 'User-added tag';
        
        // Highlight matching tags
        const isMatching = this.selectedTags.has(tagName.toLowerCase());
        const highlightStyle = isMatching ? 'box-shadow: 0 0 0 2px #fbbf24;' : '';
        
        return `
          <button type="button" data-tag="${this._escapeHtml(tagName)}"
                  class="tag-badge px-2 py-0.5 text-xs rounded-full font-medium
                         transition-all duration-200 cursor-pointer border"
                  style="background:${bgColor}; color:${textColor}; border-color:${borderColor}; ${highlightStyle}"
                  onmouseover="this.style.background='${hoverBg}'; this.style.color='white';"
                  onmouseout="this.style.background='${bgColor}'; this.style.color='${textColor}';"
                  title="${this._escapeHtml(title)}">
            ${emoji}#${this._escapeHtml(tagName)}${confidenceText}
          </button>
        `;
      }).join('');
      tagsHTML = `<div class="flex flex-wrap gap-1">${badgeItems}</div>`;
    }
    
    // Determine reaction buttons or static counts
    let reactionHTML = '';
    if (window.currentUserId) {
      const likeActive = image.user_reaction === 'like';
      const dislikeActive = image.user_reaction === 'dislike';
      
      const likeStyle = likeActive ? 'color:#0f5c4e;' : '';
      const dislikeStyle = dislikeActive ? 'color:#ea6c1a;' : '';
      
      reactionHTML = `
        <button type="button" data-image-id="${image.id}" data-reaction="like"
                data-active="${likeActive ? 'true' : 'false'}"
                class="reaction-btn flex items-center gap-1 text-sm font-medium
                       transition-colors duration-200 focus:outline-none"
                style="${likeStyle}">
          👍 <span id="likes-count-${image.id}">${image.likes || 0}</span>
        </button>
        <button type="button" data-image-id="${image.id}" data-reaction="dislike"
                data-active="${dislikeActive ? 'true' : 'false'}"
                class="reaction-btn flex items-center gap-1 text-sm font-medium
                       transition-colors duration-200 focus:outline-none"
                style="${dislikeStyle}">
          👎 <span id="dislikes-count-${image.id}">${image.dislikes || 0}</span>
        </button>
      `;
    } else {
      reactionHTML = `
        <span class="flex items-center gap-1 text-sm text-gray-400 dark:text-gray-500">
          👍 <span id="likes-count-${image.id}">${image.likes || 0}</span>
        </span>
        <span class="flex items-center gap-1 text-sm text-gray-400 dark:text-gray-500">
          👎 <span id="dislikes-count-${image.id}">${image.dislikes || 0}</span>
        </span>
      `;
    }
    
    // Download button
    const downloadHTML = `
      <a href="/download/${image.id}"
         onclick="event.stopPropagation();"
         class="${window.currentUserId && window.currentUserId === image.user_id ? '' : 'ml-auto '}text-sm text-gray-400 hover:text-blue-500 dark:text-gray-500 dark:hover:text-blue-400
                transition-colors duration-200"
         title="Download image">⬇️</a>
    `;
    
    // Delete button (only for owner)
    let deleteHTML = '';
    if (window.currentUserId && window.currentUserId === image.user_id) {
      deleteHTML = `
        <button type="button" data-image-id="${image.id}"
                class="delete-btn ml-auto text-sm text-gray-400 hover:text-red-500
                       dark:text-gray-500 dark:hover:text-red-400
                       transition-colors duration-200 focus:outline-none"
                aria-label="Delete image">🗑️</button>
      `;
    }
    
    return `
      <div id="image-card-${image.id}"
           class="break-inside-avoid mb-4 rounded-2xl shadow-md
                  overflow-hidden card-fade-in hover:shadow-xl transition-all duration-300
                  backdrop-blur-md bg-white/80 dark:bg-gray-800/80
                  border border-white/20 dark:border-gray-700/50">
        <div class="image-container overflow-hidden rounded-t-2xl">
          <img src="${this._escapeHtml(image.s3_url)}"
               alt="Uploaded by ${this._escapeHtml(image.username)}"
               loading="lazy"
               onclick="openLightbox(${image.id}, '${this._escapeHtml(image.s3_url)}', '${this._escapeHtml(image.username)}', ${image.id})"
               class="w-full object-cover cursor-pointer" />
        </div>
        <div class="p-3 space-y-2 backdrop-blur-sm bg-white/60 dark:bg-gray-800/60">
          <div class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <a href="/user/${this._escapeHtml(image.username)}"
               class="font-semibold hover:underline transition-colors duration-200"
               style="color:#0f5c4e;">
              👤 ${this._escapeHtml(image.username)}
            </a>
            <span class="text-gray-400 dark:text-gray-500">${this._escapeHtml(image.uploaded_at)}</span>
          </div>
          <div class="text-xs text-gray-400 dark:text-gray-500">
            👁️ ${image.views || 0} views
          </div>
          ${tagsHTML}
          <div class="flex items-center gap-3 pt-1">
            ${reactionHTML}
            ${downloadHTML}
            ${deleteHTML}
          </div>
        </div>
      </div>
    `;
  }
  
  /**
   * Show loading indicator
   * @private
   */
  _showLoading() {
    if (this.resultsContainer) {
      this.resultsContainer.classList.add('hidden');
    }
    if (this.loadingIndicator) {
      this.loadingIndicator.classList.remove('hidden');
    }
  }
  
  /**
   * Hide loading indicator
   * @private
   */
  _hideLoading() {
    if (this.loadingIndicator) {
      this.loadingIndicator.classList.add('hidden');
    }
    if (this.resultsContainer) {
      this.resultsContainer.classList.remove('hidden');
    }
  }
  
  /**
   * Restore the original gallery content
   * @private
   */
  _restoreOriginalGallery() {
    // Reload the page to restore original gallery
    window.location.reload();
  }
  
  /**
   * Show a toast notification
   * @private
   */
  _showToast(message, type = 'info') {
    // Use existing showToast function if available
    if (typeof showToast === 'function') {
      showToast(message, type);
    } else {
      console.log(`[${type.toUpperCase()}] ${message}`);
    }
  }
  
  /**
   * Escape HTML to prevent XSS
   * @private
   */
  _escapeHtml(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SmartSearch;
}
