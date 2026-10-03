// Pictures are shrunk in the browser before upload, so a phone photo of
// several megabytes does not have to travel to the server first. The server
// still decodes, checks and re-encodes whatever it receives.

const MAX_SIDE = 1600;

/** A JPEG of at most MAX_SIDE pixels, upright, transparency on white; or the
 * file itself if this browser cannot decode it (the server then decides). */
export async function prepareForUpload(file: File): Promise<Blob> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file); // applies the photo's orientation
  } catch {
    return file;
  }
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.fillStyle = "#fff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    return blob ?? file;
  } finally {
    bitmap.close();
  }
}
