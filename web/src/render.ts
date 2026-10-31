// Page rendering and the image-URL check (SR-003, change 0002). No imports, and the Document is a
// parameter, so the node tests run this file with a fake document. Erasable TypeScript only.

export type Dog = { breed: string; url: string };

// The image-host rule of SPEC 1.5; the CSP narrows it to the one deployed bucket.
const IMAGE_HOST = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\.s3\.eu-north-1\.amazonaws\.com$/;

export function isImageUrl(url: unknown): boolean {
  if (typeof url !== "string") return false;
  let u: URL;
  try {
    u = new URL(url); // no base: relative and protocol-relative URLs throw
  } catch {
    return false;
  }
  return (
    u.protocol === "https:" &&
    u.username === "" &&
    u.password === "" &&
    u.port === "" &&
    IMAGE_HOST.test(u.hostname)
  );
}

// API data only ever becomes text: textContent, alt, option text and value.
export function renderDogs(doc: Document, grid: HTMLElement, status: HTMLElement, dogs: Dog[]): void {
  const shown = dogs.filter((d) => isImageUrl(d.url));
  grid.replaceChildren(
    ...shown.map((d) => {
      const fig = doc.createElement("figure");
      const img = doc.createElement("img");
      img.src = d.url;
      img.alt = d.breed;
      img.loading = "lazy";
      const cap = doc.createElement("figcaption");
      cap.textContent = d.breed;
      fig.append(img, cap);
      return fig;
    }),
  );
  status.textContent = `${shown.length} dog${shown.length === 1 ? "" : "s"}`;
}

export function renderBreeds(doc: Document, select: HTMLSelectElement, dogs: Dog[]): void {
  for (const breed of [...new Set(dogs.map((d) => d.breed))].sort()) {
    const opt = doc.createElement("option");
    opt.value = breed;
    opt.textContent = breed;
    select.append(opt);
  }
}
