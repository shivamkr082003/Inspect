# Image Integration Testing Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features (objects, edges, textures, shadows).
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
- If the image is animated, extract the first frame only.
- Resize large images to reasonable bounds.
- Sample inspection photos for testing are available at /app/template/sample_photos/ (17 real product photos).
