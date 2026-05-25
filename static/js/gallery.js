/**
 * gallery.js — Frontend JavaScript for the CMS Image Gallery
 *
 * Modules:
 *   1. Search     — debounced tag search with fetch and DOM update (Req 6.1–6.5, 6.7, 6.8)
 *   2. Reaction   — like/dislike via fetch with count update (Req 8.1, 8.9, 8.10)
 *   3. Delete     — delete media card via fetch with DOM removal (Req 7.8)
 *   4. Lightbox   — fullscreen image viewer with view tracking
 *   5. Toast      — non-blocking notifications
 *
 * Note: Theme toggle is handled entirely in base.html to avoid duplicate handlers.
 */

/* ======================================================================
   Download Helper Function (deprecated - now using direct links)
   ====================================================================== */

/* ======================================================================
   Toast Notification System
   ====================================================================== */

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `fixed top-24 right-4 z-50 px-6 py-3 rounded-xl shadow-lg text-white text-sm font-medium
                     transform transition-all duration-300 translate-x-0 opacity-100`;
  
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

/* ======================================================================
   Lightbox Modal System
   ====================================================================== */

function openLightbox(imageId, imageUrl, username, imageIdForView) {
  const modal = document.getElementById('lightbox-modal');
  const img = document.getElementById('lightbox-image');
  const usernameEl = document.getElementById('lightbox-username');
  const viewsEl = document.getElementById('lightbox-views');
  const downloadBtn = document.getElementById('lightbox-download');
  
  if (!modal || !img) return;
  
  // Set image and info
  img.src = imageUrl;
  img.alt = `Uploaded by ${username}`;
  if (usernameEl) usernameEl.textContent = `👤 ${username}`;
  // Set download button to use the download route
  if (downloadBtn) downloadBtn.href = `/download/${imageIdForView}`;
  
  // Show modal
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  
  // Increment view count
  fetch(`/image/${imageIdForView}/view`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(res => res.json())
  .then(data => {
    if (data.views && viewsEl) {
      viewsEl.textContent = `👁️ ${data.views} views`;
    }
  })
  .catch(err => console.error('View tracking failed:', err));
}

function closeLightbox() {
  const modal = document.getElementById('lightbox-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

// Make functions global so onclick can access them
window.openLightbox = openLightbox;
window.closeLightbox = closeLightbox;

/* ======================================================================
   DOMContentLoaded — wire up all interactive modules after DOM is ready
   ====================================================================== */
document.addEventListener('DOMContentLoaded', function () {

  /* ====================================================================
     Lightbox Close Handlers
     ==================================================================== */
  
  const lightboxClose = document.getElementById('lightbox-close');
  const lightboxModal = document.getElementById('lightbox-modal');
  
  if (lightboxClose) {
    lightboxClose.addEventListener('click', closeLightbox);
  }
  
  if (lightboxModal) {
    // Close on backdrop click
    lightboxModal.addEventListener('click', function(e) {
      if (e.target === lightboxModal) closeLightbox();
    });
    
    // Close on Escape key
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && !lightboxModal.classList.contains('hidden')) {
        closeLightbox();
      }
    });
  }

  /* ====================================================================
     MODULE 1 — Search
     Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8
     ==================================================================== */

  var searchInput = document.getElementById('search-input');
  var searchBtn = document.getElementById('search-btn');
  var galleryGrid = document.getElementById('gallery-grid');
  var noResults = document.getElementById('no-results');
  var skeletonLoader = document.getElementById('skeleton-loader');

  /* Store the original gallery HTML on load so it can be restored (Req 6.5) */
  var originalGalleryHTML = galleryGrid ? galleryGrid.innerHTML : '';

  /* Debounce timer handle */
  var debounceTimer = null;

  /**
   * Show a toast/alert with an error message without updating the grid.
   * Requirement 6.7 — on fetch error, display message and leave grid intact.
   *
   * @param {string} message - The error message to display.
   */
  function showSearchError(message) {
    /* Use toast notification instead of alert */
    showToast(message, 'error');
  }

  /**
   * Render a single image card as an HTML string.
   * Matches the card structure used in index.html.
   * Uses window.currentUserId to determine if the delete button should appear.
   *
   * @param {Object} image - Image data dict from the search API.
   * @returns {string} HTML string for the card.
   */
  function renderCard(image) {
    /* Build tag badge HTML for each tag with AI detection */
    var tagsHTML = '';
    if (image.tag_data && image.tag_data.length > 0) {
      var badgeItems = image.tag_data.map(function (tagInfo) {
        var isAI = tagInfo.is_ai;
        var confidence = tagInfo.confidence;
        var tagName = tagInfo.name;
        
        var bgColor = isAI ? '#e8f4ff' : '#f0faf7';
        var textColor = isAI ? '#0066cc' : '#0f5c4e';
        var borderColor = isAI ? '#99ccff' : '#a1e0cc';
        var hoverBg = isAI ? '#0066cc' : '#0f5c4e';
        var emoji = isAI ? '🤖' : '';
        var confidenceText = isAI && confidence ? ' <span style="opacity:0.7; font-size:0.85em;">(' + Math.round(confidence) + '%)</span>' : '';
        var title = isAI ? 'AI-generated (' + Math.round(confidence) + '% confidence)' : 'User-added tag';
        
        return (
          '<button type="button" data-tag="' + escapeAttr(tagName) + '" ' +
          'class="tag-badge px-2 py-0.5 text-xs rounded-full font-medium ' +
          'transition-all duration-200 cursor-pointer border" ' +
          'style="background:' + bgColor + '; color:' + textColor + '; border-color:' + borderColor + ';" ' +
          'onmouseover="this.style.background=\'' + hoverBg + '\'; this.style.color=\'white\';" ' +
          'onmouseout="this.style.background=\'' + bgColor + '\'; this.style.color=\'' + textColor + '\';" ' +
          'title="' + escapeAttr(title) + '">' +
          emoji + '#' + escapeHTML(tagName) + confidenceText +
          '</button>'
        );
      });
      tagsHTML = '<div class="flex flex-wrap gap-1">' + badgeItems.join('') + '</div>';
    } else if (image.tags && image.tags.length > 0) {
      /* Fallback for old format without tag_data */
      var badgeItems = image.tags.map(function (tag) {
        return (
          '<button type="button" data-tag="' + escapeAttr(tag) + '" ' +
          'class="tag-badge px-2 py-0.5 text-xs rounded-full font-medium ' +
          'transition-all duration-200 cursor-pointer border" ' +
          'style="background:#f0faf7; color:#0f5c4e; border-color:#a1e0cc;" ' +
          'onmouseover="this.style.background=\'#0f5c4e\'; this.style.color=\'white\';" ' +
          'onmouseout="this.style.background=\'#f0faf7\'; this.style.color=\'#0f5c4e\';">' +
          '#' + escapeHTML(tag) +
          '</button>'
        );
      });
      tagsHTML = '<div class="flex flex-wrap gap-1">' + badgeItems.join('') + '</div>';
    }

    /* Determine whether to show like/dislike buttons or static counts.
       Buttons are shown only when a user is authenticated (window.currentUserId set). */
    var reactionHTML = '';
    if (window.currentUserId) {
      /* Authenticated user — show interactive like/dislike buttons */
      var likeActive = image.user_reaction === 'like';
      var dislikeActive = image.user_reaction === 'dislike';
      
      var likeStyle = likeActive ? 'color:#0f5c4e;' : '';
      var likeHoverOut = likeActive ? '#0f5c4e' : '';
      var likeHoverIn = likeActive ? '#0a4038' : '#0f5c4e';
      
      var dislikeStyle = dislikeActive ? 'color:#ea6c1a;' : '';
      var dislikeHoverOut = dislikeActive ? '#ea6c1a' : '';
      var dislikeHoverIn = dislikeActive ? '#c2540e' : '#ea6c1a';
      
      reactionHTML =
        '<button type="button" data-image-id="' + image.id + '" data-reaction="like" ' +
        'data-active="' + (likeActive ? 'true' : 'false') + '" ' +
        'class="reaction-btn flex items-center gap-1 text-sm font-medium ' +
        'transition-colors duration-200 focus:outline-none" ' +
        'style="' + likeStyle + '" ' +
        'onmouseover="this.style.color=\'' + likeHoverIn + '\';" ' +
        'onmouseout="this.style.color=\'' + likeHoverOut + '\';">' +
        '👍 <span id="likes-count-' + image.id + '" class="font-medium">' + (image.likes || 0) + '</span>' +
        '</button>' +
        '<button type="button" data-image-id="' + image.id + '" data-reaction="dislike" ' +
        'data-active="' + (dislikeActive ? 'true' : 'false') + '" ' +
        'class="reaction-btn flex items-center gap-1 text-sm font-medium ' +
        'transition-colors duration-200 focus:outline-none" ' +
        'style="' + dislikeStyle + '" ' +
        'onmouseover="this.style.color=\'' + dislikeHoverIn + '\';" ' +
        'onmouseout="this.style.color=\'' + dislikeHoverOut + '\';">' +
        '👎 <span id="dislikes-count-' + image.id + '" class="font-medium">' + (image.dislikes || 0) + '</span>' +
        '</button>';
    } else {
      /* Guest — show static counts without interactive buttons */
      reactionHTML =
        '<span class="flex items-center gap-1 text-sm text-gray-400 dark:text-gray-500">' +
        '👍 <span id="likes-count-' + image.id + '">' + (image.likes || 0) + '</span>' +
        '</span>' +
        '<span class="flex items-center gap-1 text-sm text-gray-400 dark:text-gray-500">' +
        '👎 <span id="dislikes-count-' + image.id + '">' + (image.dislikes || 0) + '</span>' +
        '</span>';
    }

    /* Download button - always show */
    var downloadHTML = 
      '<a href="/download/' + image.id + '" ' +
      'onclick="event.stopPropagation();" ' +
      'class="' + (window.currentUserId && window.currentUserId === image.user_id ? '' : 'ml-auto ') + 
      'text-sm text-gray-400 hover:text-blue-500 dark:text-gray-500 dark:hover:text-blue-400 ' +
      'transition-colors duration-200" ' +
      'title="Download image">⬇️</a>';

    /* Show delete button only if the current user owns this image */
    var deleteHTML = '';
    if (window.currentUserId && window.currentUserId === image.user_id) {
      deleteHTML =
        '<button type="button" data-image-id="' + image.id + '" ' +
        'class="delete-btn ml-auto text-sm text-gray-400 hover:text-red-500 ' +
        'dark:text-gray-500 dark:hover:text-red-400 ' +
        'transition-colors duration-200 focus:outline-none" ' +
        'aria-label="Delete image">🗑️</button>';
    }

    /* Assemble the full card HTML matching the structure in index.html */
    return (
      '<div id="image-card-' + image.id + '" ' +
      'class="break-inside-avoid mb-4 rounded-2xl shadow-md ' +
      'overflow-hidden card-fade-in hover:shadow-xl transition-all duration-300 ' +
      'backdrop-blur-md bg-white/80 dark:bg-gray-800/80 ' +
      'border border-white/20 dark:border-gray-700/50">' +

        '<div class="image-container overflow-hidden rounded-t-2xl">' +
          '<img src="' + escapeAttr(image.s3_url) + '" ' +
          'alt="Uploaded by ' + escapeAttr(image.username) + '" ' +
          'loading="lazy" ' +
          'onclick="openLightbox(' + image.id + ', \'' + escapeAttr(image.s3_url) + '\', \'' + escapeAttr(image.username) + '\', ' + image.id + ')" ' +
          'class="w-full object-cover cursor-pointer" />' +
        '</div>' +

        '<div class="p-3 space-y-2 backdrop-blur-sm bg-white/60 dark:bg-gray-800/60">' +

          '<div class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">' +
            '<a href="/user/' + escapeAttr(image.username) + '" ' +
            'class="font-semibold hover:underline transition-colors duration-200" ' +
            'style="color:#0f5c4e;">👤 ' + escapeHTML(image.username) + '</a>' +
            '<span class="text-gray-400 dark:text-gray-500">' + escapeHTML(image.uploaded_at) + '</span>' +
          '</div>' +

          '<div class="text-xs text-gray-400 dark:text-gray-500">' +
            '👁️ ' + (image.views || 0) + ' views' +
          '</div>' +

          tagsHTML +

          '<div class="flex items-center gap-3 pt-1">' +
            reactionHTML +
            downloadHTML +
            deleteHTML +
          '</div>' +

        '</div>' +
      '</div>'
    );
  }

  /**
   * Escape a string for safe insertion into HTML text content.
   *
   * @param {string} str - Raw string to escape.
   * @returns {string} HTML-escaped string.
   */
  function escapeHTML(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Escape a string for safe use in an HTML attribute value.
   *
   * @param {string} str - Raw string to escape.
   * @returns {string} Attribute-safe escaped string.
   */
  function escapeAttr(str) {
    return escapeHTML(str);
  }

  /**
   * Execute a search against GET /search?q=<query> and update the gallery grid.
   * On success, replaces grid content with rendered cards or shows no-results.
   * On error, shows an error message without touching the grid (Req 6.7).
   *
   * @param {string} query - The search query string.
   */
  function executeSearch(query) {
    /* Trim the query and validate it has at least one non-whitespace char (Req 6.1) */
    var trimmed = query.trim();

    if (trimmed.length === 0) {
      /* Empty or all-whitespace query — restore original gallery (Req 6.5, 6.8) */
      restoreGallery();
      return;
    }

    /* Show skeleton loader while searching */
    if (galleryGrid) {
      galleryGrid.classList.add('hidden');
    }
    if (skeletonLoader) {
      skeletonLoader.classList.remove('hidden');
    }
    if (noResults) {
      noResults.classList.add('hidden');
    }

    /* Call the search endpoint via fetch (Requirement 6.2) */
    fetch('/search?q=' + encodeURIComponent(trimmed))
      .then(function (response) {
        /* Check for HTTP-level errors (Requirement 6.7) */
        if (!response.ok) {
          return response.json().then(function (errData) {
            throw new Error(errData.error || 'Search request failed');
          });
        }
        return response.json();
      })
      .then(function (results) {
        /* Hide skeleton loader */
        if (skeletonLoader) {
          skeletonLoader.classList.add('hidden');
        }
        if (galleryGrid) {
          galleryGrid.classList.remove('hidden');
        }

        /* Hide the no-results message before updating the grid */
        if (noResults) {
          noResults.classList.add('hidden');
        }

        if (!Array.isArray(results) || results.length === 0) {
          /* No matching results — clear grid and show no-results message (Req 6.4) */
          if (galleryGrid) {
            galleryGrid.innerHTML = '';
          }
          if (noResults) {
            noResults.classList.remove('hidden');
          }
          return;
        }

        /* Render all result cards into a masonry wrapper (Requirement 6.3) */
        var masonryHTML =
          '<div class="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-4">' +
          results.map(renderCard).join('') +
          '</div>';

        /* Replace the gallery grid content with the search results (Req 6.3) */
        if (galleryGrid) {
          galleryGrid.innerHTML = masonryHTML;
        }
      })
      .catch(function (err) {
        /* Hide skeleton loader on error */
        if (skeletonLoader) {
          skeletonLoader.classList.add('hidden');
        }
        if (galleryGrid) {
          galleryGrid.classList.remove('hidden');
        }
        /* Fetch or parse error — show error message, do NOT update grid (Req 6.7) */
        showSearchError(err.message || 'An unexpected error occurred.');
      });
  }

  /**
   * Restore the gallery grid to its original server-rendered HTML.
   * Called when the search bar is cleared (Requirement 6.5).
   */
  function restoreGallery() {
    if (skeletonLoader) {
      skeletonLoader.classList.add('hidden');
    }
    if (galleryGrid) {
      galleryGrid.classList.remove('hidden');
      galleryGrid.innerHTML = originalGalleryHTML;
    }
    /* Hide the no-results message when restoring the full gallery */
    if (noResults) {
      noResults.classList.add('hidden');
    }
  }

  if (searchInput) {
    /* Debounced input listener — fires search 300 ms after the user stops typing */
    searchInput.addEventListener('input', function () {
      var query = searchInput.value;

      /* Clear any pending debounce timer */
      clearTimeout(debounceTimer);

      /* If the input is empty or all whitespace, restore immediately (Req 6.5, 6.8) */
      if (query.trim().length === 0) {
        restoreGallery();
        return;
      }

      /* Schedule the search after 300 ms of inactivity (Requirement 6.1) */
      debounceTimer = setTimeout(function () {
        executeSearch(query);
      }, 300);
    });

    /* Enter key listener on the search input — triggers immediate search (Req 6.2) */
    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        /* Cancel any pending debounce and search immediately */
        clearTimeout(debounceTimer);
        executeSearch(searchInput.value);
      }
    });
  }

  if (searchBtn) {
    /* Search button click — triggers immediate search (Requirement 6.2) */
    searchBtn.addEventListener('click', function () {
      clearTimeout(debounceTimer);
      executeSearch(searchInput ? searchInput.value : '');
    });
  }

  /* Tag badge click — fill search input and trigger search (Requirement 6.2) */
  document.addEventListener('click', function (event) {
    var target = event.target;

    /* Walk up the DOM to find a tag-badge element */
    var tagBadge = target.closest ? target.closest('[data-tag]') : null;
    if (!tagBadge) {
      /* Fallback for browsers without closest() */
      if (target.hasAttribute && target.hasAttribute('data-tag')) {
        tagBadge = target;
      }
    }

    if (tagBadge) {
      var tagText = tagBadge.getAttribute('data-tag');
      if (tagText && searchInput) {
        /* Fill the search input with the tag text */
        searchInput.value = tagText;
        /* Cancel any pending debounce and trigger search immediately */
        clearTimeout(debounceTimer);
        executeSearch(tagText);
      }
    }
  });

  /* ====================================================================
     MODULE 3 — Reaction (like / dislike)
     Requirements: 8.1, 8.9, 8.10
     ==================================================================== */

  /**
   * Event delegation on document for clicks on elements with data-reaction attribute.
   * Extracts data-image-id and data-reaction, calls POST /like/<id>,
   * updates count badges on success, redirects to /login on 401 (Req 8.10).
   */
  document.addEventListener('click', function (event) {
    var target = event.target;

    /* Walk up the DOM to find a button with data-reaction */
    var reactionBtn = target.closest ? target.closest('[data-reaction]') : null;
    if (!reactionBtn) {
      if (target.hasAttribute && target.hasAttribute('data-reaction')) {
        reactionBtn = target;
      }
    }

    if (!reactionBtn) return;

    /* Extract the image id and reaction type from the button's data attributes */
    var imageId = reactionBtn.getAttribute('data-image-id');
    var reactionType = reactionBtn.getAttribute('data-reaction');

    if (!imageId || !reactionType) return;

    /* Add bounce animation to the button */
    reactionBtn.classList.add('reaction-bounce');
    setTimeout(function() {
      reactionBtn.classList.remove('reaction-bounce');
    }, 500);

    /* Get both buttons for this image */
    var likeBtn = document.querySelector('[data-image-id="' + imageId + '"][data-reaction="like"]');
    var dislikeBtn = document.querySelector('[data-image-id="' + imageId + '"][data-reaction="dislike"]');

    /* Optimistically update UI immediately */
    var currentState = reactionBtn.getAttribute('data-active');
    var isCurrentlyActive = currentState === 'true';

    if (reactionType === 'like') {
      if (isCurrentlyActive) {
        /* Toggle off */
        likeBtn.setAttribute('data-active', 'false');
        likeBtn.style.color = '';
      } else {
        /* Toggle on, turn off dislike */
        likeBtn.setAttribute('data-active', 'true');
        likeBtn.style.color = '#0f5c4e';
        if (dislikeBtn) {
          dislikeBtn.setAttribute('data-active', 'false');
          dislikeBtn.style.color = '';
        }
      }
    } else {
      if (isCurrentlyActive) {
        /* Toggle off */
        dislikeBtn.setAttribute('data-active', 'false');
        dislikeBtn.style.color = '';
      } else {
        /* Toggle on, turn off like */
        dislikeBtn.setAttribute('data-active', 'true');
        dislikeBtn.style.color = '#ea6c1a';
        if (likeBtn) {
          likeBtn.setAttribute('data-active', 'false');
          likeBtn.style.color = '';
        }
      }
    }

    /* Call POST /like/<image_id> with JSON body (Requirement 8.1) */
    fetch('/like/' + encodeURIComponent(imageId), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reaction: reactionType }),
    })
      .then(function (response) {
        if (response.status === 401) {
          /* Unauthenticated — redirect to login page (Requirement 8.10) */
          window.location.href = '/login';
          return null;
        }

        if (!response.ok) {
          return response.json().then(function (errData) {
            throw new Error(errData.error || 'Reaction request failed');
          });
        }

        return response.json();
      })
      .then(function (data) {
        if (!data) return; /* Redirected — nothing to update */

        /* Update the like and dislike count badges on the card with animation (Requirement 8.9) */
        var likesEl = document.getElementById('likes-count-' + imageId);
        var dislikesEl = document.getElementById('dislikes-count-' + imageId);

        if (likesEl && data.likes !== undefined) {
          animateCountChange(likesEl, data.likes);
        }
        if (dislikesEl && data.dislikes !== undefined) {
          animateCountChange(dislikesEl, data.dislikes);
        }
      })
      .catch(function (err) {
        /* Show a non-blocking toast on reaction error */
        showToast('Reaction error: ' + (err.message || 'An unexpected error occurred.'), 'error');
        
        /* Revert optimistic update on error */
        if (reactionType === 'like') {
          if (isCurrentlyActive) {
            likeBtn.setAttribute('data-active', 'true');
            likeBtn.style.color = '#0f5c4e';
          } else {
            likeBtn.setAttribute('data-active', 'false');
            likeBtn.style.color = '';
          }
        } else {
          if (isCurrentlyActive) {
            dislikeBtn.setAttribute('data-active', 'true');
            dislikeBtn.style.color = '#ea6c1a';
          } else {
            dislikeBtn.setAttribute('data-active', 'false');
            dislikeBtn.style.color = '';
          }
        }
      });
  });

  /**
   * Animate count change with smooth transition
   * @param {HTMLElement} element - The count element to animate
   * @param {number} newValue - The new count value
   */
  function animateCountChange(element, newValue) {
    /* Add animation class */
    element.classList.add('count-animate');
    
    /* Update the text content */
    element.textContent = newValue;
    
    /* Remove animation class after animation completes */
    setTimeout(function() {
      element.classList.remove('count-animate');
    }, 300);
  }

  /* ====================================================================
     MODULE 4 — Delete
     Requirements: 7.8
     ==================================================================== */

  /* ====================================================================
     MODULE 3 — Delete
     Requirements: 7.8
     Shows a confirmation modal before deleting. Only proceeds on confirm.
     ==================================================================== */

  var pendingDeleteId = null; /* stores the image id waiting for confirmation */

  var deleteModal    = document.getElementById('delete-modal');
  var deleteModalBox = document.getElementById('delete-modal-box');
  var cancelBtn      = document.getElementById('delete-cancel-btn');
  var confirmBtn     = document.getElementById('delete-confirm-btn');

  /* Helper: open the modal with a pop-in animation */
  function openDeleteModal(imageId) {
    pendingDeleteId = imageId;
    deleteModal.classList.remove('hidden');
    deleteModal.classList.add('flex');
    /* Trigger scale-in animation */
    setTimeout(function () {
      deleteModalBox.style.transform = 'scale(1)';
      deleteModalBox.style.opacity = '1';
    }, 10);
  }

  /* Helper: close the modal and reset state */
  function closeDeleteModal() {
    deleteModalBox.style.transform = 'scale(0.95)';
    deleteModalBox.style.opacity = '0';
    setTimeout(function () {
      deleteModal.classList.add('hidden');
      deleteModal.classList.remove('flex');
      pendingDeleteId = null;
    }, 150);
  }

  /* Close on Cancel button */
  if (cancelBtn) {
    cancelBtn.addEventListener('click', closeDeleteModal);
  }

  /* Close on backdrop click (outside the modal box) */
  if (deleteModal) {
    deleteModal.addEventListener('click', function (e) {
      if (e.target === deleteModal) closeDeleteModal();
    });
  }

  /* Close on Escape key */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && pendingDeleteId) closeDeleteModal();
  });

  /* Confirm button — actually perform the delete */
  if (confirmBtn) {
    confirmBtn.addEventListener('click', function () {
      var imageId = pendingDeleteId;
      if (!imageId) return;
      closeDeleteModal();

      fetch('/delete/' + encodeURIComponent(imageId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (errData) {
              throw new Error(errData.error || 'Delete request failed');
            });
          }
          return response.json();
        })
        .then(function (data) {
          if (data && data.success) {
            /* Remove the card from the DOM without a page reload (Req 7.8) */
            var card = document.getElementById('image-card-' + imageId);
            if (card) {
              card.style.transition = 'opacity 0.3s, transform 0.3s';
              card.style.opacity = '0';
              card.style.transform = 'scale(0.95)';
              setTimeout(function () { card.remove(); }, 300);
            }
          } else {
            showToast('Delete failed: ' + (data && data.error ? data.error : 'Unknown error'), 'error');
          }
        })
        .catch(function (err) {
          showToast('Delete error: ' + (err.message || 'An unexpected error occurred.'), 'error');
        });
    });
  }

  /* Event delegation — intercept delete button clicks to show modal */
  document.addEventListener('click', function (event) {
    var target = event.target;
    var deleteBtn = target.closest ? target.closest('.delete-btn') : null;
    if (!deleteBtn && target.classList && target.classList.contains('delete-btn')) {
      deleteBtn = target;
    }
    if (!deleteBtn) return;

    var imageId = deleteBtn.getAttribute('data-image-id');
    if (!imageId) return;

    /* Show confirmation modal instead of deleting immediately */
    openDeleteModal(imageId);
  });

}); /* end DOMContentLoaded */
