document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.querySelector(".drop-zone");
  const fileInput = document.getElementById("report-input");
  const uploadForm = document.getElementById("upload-form");
  const fileListContainer = document.getElementById("file-list");

  // Store File objects in a mutable array
  let selectedFiles = [];

  if (dropZone) {
    // Trigger file input click
    dropZone.addEventListener("click", () => {
      fileInput.click();
    });

    // Drag over
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("drag");
    });

    // Drag leave
    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("drag");
    });

    // Drop
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag");
      const droppedFiles = Array.from(e.dataTransfer.files);
      addFiles(droppedFiles);
    });
  }

  // Update file list on change
  fileInput.addEventListener("change", (event) => {
    const newFiles = Array.from(event.target.files);
    addFiles(newFiles);
    // Reset the input so the same file can be selected again if removed
    fileInput.value = "";
  });

  // Handle form submission with Fetch API
  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault(); // Prevent default page reload

    const submitButton = uploadForm.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.textContent = "Uploading...";

    const formData = new FormData();

    // CRITICAL FIX: Get the patient name and append it to FormData
    const patientName = uploadForm
      .querySelector('input[name="patient"]')
      .value.trim();
    if (!patientName) {
      showToast("Patient name is required.", "error");
      submitButton.disabled = false;
      submitButton.textContent = originalButtonText;
      return;
    }
    formData.append("patient", patientName);

    selectedFiles.forEach((file) => {
      formData.append("report", file);
    });

    try {
      const response = await fetch(uploadForm.action, {
        method: "POST",
        body: formData,
      });
      const result = await response.json();

      if (response.ok) {
        showToast(result.success, "success");
        selectedFiles = []; // Clear files after successful upload
        updateFileList();
        uploadForm.reset(); // Clear patient name
      } else {
        showToast(result.error || "An unknown error occurred.", "error");
      }
    } catch (error) {
      showToast("Network error. Please try again.", "error");
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalButtonText;
    }
  });

  function addFiles(files) {
    const allowedExtensions = [
      "pdf",
      "png",
      "jpg",
      "jpeg",
      "gif",
      "mp4",
      "mov",
      "webm",
    ];
    let validFiles = [];
    let invalidFiles = [];

    files.forEach((file) => {
      const extension = file.name.split(".").pop().toLowerCase();
      if (allowedExtensions.includes(extension)) {
        validFiles.push(file);
      } else {
        invalidFiles.push(file.name);
      }
    });

    selectedFiles = [...selectedFiles, ...validFiles];
    if (invalidFiles.length > 0) {
      showToast(`Invalid file type(s): ${invalidFiles.join(", ")}`, "error");
    }
    updateFileList();
  }

  function updateFileList() {
    fileListContainer.innerHTML = ""; // Clear previous list

    if (selectedFiles.length === 0) {
      fileListContainer.style.display = "block"; // Ensure it's visible to show the message
      const noFileMessage = document.createElement("p");
      noFileMessage.className = "no-files-selected-message";
      noFileMessage.textContent = "No files selected.";
      fileListContainer.appendChild(noFileMessage);
      return;
    }

    fileListContainer.style.display = "block";
    const list = document.createElement("ul");
    selectedFiles.forEach((file, index) => {
      const item = document.createElement("li");
      item.className = "selected-file-item";

      const fileNameSpan = document.createElement("span");
      fileNameSpan.textContent = file.name;
      item.appendChild(fileNameSpan);

      const deleteButton = document.createElement("button");
      deleteButton.className = "delete-file-btn";
      deleteButton.innerHTML = "&times;"; // 'x' icon
      deleteButton.addEventListener("click", (e) => {
        e.stopPropagation(); // Prevent dropZone click event
        removeFile(index);
      });
      item.appendChild(deleteButton);
      list.appendChild(item);
    });
    fileListContainer.appendChild(list);
  }

  function removeFile(index) {
    selectedFiles.splice(index, 1); // Remove file from array
    updateFileList(); // Re-render the list
  }

  // Call updateFileList initially to display the "No files selected" placeholder
  updateFileList();
});
