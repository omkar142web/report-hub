document.addEventListener("DOMContentLoaded", () => {
  const delLinks = document.querySelectorAll(".delete");
  delLinks.forEach((l) => {
    l.addEventListener("click", (e) => {
      // The confirm dialog will pause execution. If the user clicks "Cancel",
      // preventDefault() stops the browser from navigating to the delete link.
      if (!confirm("Are you sure you want to delete this report?")) {
        e.preventDefault();
      }
    });
  });
});
