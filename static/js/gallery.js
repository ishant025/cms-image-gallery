/**
 * gallery.js — Frontend JavaScript for the CMS Image Gallery
 *
 * Modules:
 *   1. Search     — debounced tag search with fetch and DOM update (Req 6.1–6.5, 6.7, 6.8)
 *   2. Reaction   — like/dislike via fetch with count update (Req 8.1, 8.9, 8.10)
 *   3. Delete     — delete media card via fetch with DOM removal (Req 7.8)
 *
 * Note: Theme toggle is handled entirely in base.html to avoid duplicate handlers.
 */

/* ======================================================================
   DOMContentLoaded — wire up all interactive modules after DOM is ready
   ====================================================================== */
document.addEventListener('DOMContentLoaded', function () {

  /* ====================================================================
     MODULE 1 — Search
     Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8
     ==================================================================== */

  var searchInput = document.getElementById('search-input');
  var searchBtn = document.getElementById('search-btn');
  var galleryGrid = document.getElementById('gallery-grid');
  var noResults = document.getElementById('no-results');

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
    /* Use a simple alert as the toast mechanism */
    alert('Search error: ' + message);
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
    /* Build tag badge HTML for each tag */
    var tagsHTML = '';
    if (image.tags && image.tags.length > 0) {
      var badgeItems = image.tags.map(function (tag) {
        return (
          '<button type="button" data-tag="' + escapeAttr(tag) + '" ' +
          'class="tag-badge px-2 py-0.5 text-xs rounded-full ' +
          'bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 ' +
          'hover:bg-indigo-200 dark:hover:bg-indigo-800 ' +
          'transition-colors duration-200 cursor-pointer">' +
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
      /* Authenticated user — show interactive like/dislike buttons (Req 5.9) */
      reactionHTML =
        '<button type="button" data-image-id="' + image.id + '" data-reaction="like" ' +
        'class="reaction-btn flex items-center gap-1 text-sm ' +
        'text-gray-600 dark:text-gray-400 hover:text-green-600 dark:hover:text-green-400 ' +
        'transition-colors duration-200 focus:outline-none">' +
        '👍 <span id="likes-count-' + image.id + '" class="font-medium">' + (image.likes || 0) + '</span>' +
        '</button>' +
        '<button type="button" data-image-id="' + image.id + '" data-reaction="dislike" ' +
        'class="reaction-btn flex items-center gap-1 text-sm ' +
        'text-gray-600 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400 ' +
        'transition-colors duration-200 focus:outline-none">' +
        '👎 <span id="dislikes-count-' + image.id + '" class="font-medium">' + (image.dislikes || 0) + '</span>' +
        '</button>';
    } else {
      /* Guest — show static counts without interactive buttons */
      reactionHTML =
        '<span class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">' +
        '👍 <span id="likes-count-' + image.id + '">' + (image.likes || 0) + '</span>' +
        '</span>' +
        '<span class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">' +
        '👎 <span id="dislikes-count-' + image.id + '">' + (image.dislikes || 0) + '</span>' +
        '</span>';
    }

    /* Show delete button only if the current user owns this image (Req 5.8) */
    var deleteHTML = '';
    if (window.currentUserId && window.currentUserId === image.user_id) {
      deleteHTML =
        '<button type="button" data-image-id="' + image.id + '" ' +
        'class="delete-btn ml-auto text-sm text-red-400 hover:text-red-600 ' +
        'dark:text-red-500 dark:hover:text-red-400 ' +
        'transition-colors duration-200 focus:outline-none" ' +
        'aria-label="Delete image">🗑️</button>';
    }

    /* Assemble the full card HTML matching the structure in index.html */
    return (
      '<div id="image-card-' + image.id + '" ' +
      'class="break-inside-avoid mb-4 bg-white dark:bg-gray-800 rounded-xl shadow-md ' +
      'overflow-hidden card-fade-in hover:shadow-xl transition-shadow duration-300">' +

        '<div class="overflow-hidden">' +
          '<img src="' + escapeAttr(image.s3_url) + '" ' +
          'alt="Uploaded by ' + escapeAttr(image.username) + '" ' +
          'loading="lazy" ' +
          'class="w-full object-cover rounded-t-xl transition-transform duration-300 hover:scale-105" />' +
        '</div>' +

        '<div class="p-3 space-y-2">' +

          '<div class="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">' +
            '<span class="font-medium text-gray-700 dark:text-gray-300">👤 ' + escapeHTML(image.username) + '</span>' +
            '<span>' + escapeHTML(image.uploaded_at) + '</span>' +
          '</div>' +

          tagsHTML +

          '<div class="flex items-center gap-3 pt-1">' +
            reactionHTML +
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
        /* Fetch or parse error — show error message, do NOT update grid (Req 6.7) */
        showSearchError(err.message || 'An unexpected error occurred.');
      });
  }

  /**
   * Restore the gallery grid to its original server-rendered HTML.
   * Called when the search bar is cleared (Requirement 6.5).
   */
  function restoreGallery() {
    if (galleryGrid) {
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

        /* Update the like and dislike count badges on the card (Requirement 8.9) */
        var likesEl = document.getElementById('likes-count-' + imageId);
        var dislikesEl = document.getElementById('dislikes-count-' + imageId);

        if (likesEl) {
          likesEl.textContent = data.likes;
        }
        if (dislikesEl) {
          dislikesEl.textContent = data.dislikes;
        }
      })
      .catch(function (err) {
        /* Show a non-blocking alert on reaction error */
        alert('Reaction error: ' + (err.message || 'An unexpected error occurred.'));
      });
  });

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
            alert('Delete failed: ' + (data && data.error ? data.error : 'Unknown error'));
          }
        })
        .catch(function (err) {
          alert('Delete error: ' + (err.message || 'An unexpected error occurred.'));
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
