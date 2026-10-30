import { type FormEvent, useEffect, useState } from "react";

import { ApiError, AuthError, fetchFirmware, uploadFirmware } from "../api";
import { formatRelative } from "../format";
import type { Firmware } from "../types";

const MAX_BYTES = 1024 * 1024; // the API's limit

interface Props {
  now: number;
  canUpload: boolean;
  onAuthError: (err: AuthError) => void;
}

/** Uploaded firmware images (Phase 15e). Everyone can see them; only ADMIN can upload. */
export function FirmwareLibrary({ now, canUpload, onAuthError }: Props) {
  const [images, setImages] = useState<Firmware[] | null>(null);
  const [version, setVersion] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchFirmware(controller.signal)
      .then(setImages)
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        if (err instanceof AuthError) return onAuthError(err);
        setMessage({ ok: false, text: err instanceof ApiError ? err.message : "Unexpected error" });
      });
    return () => controller.abort();
  }, [reload, onAuthError]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setMessage({ ok: false, text: "Firmware larger than 1 MiB" });
      return;
    }
    setBusy(true);
    try {
      // The API accepts A-Z a-z 0-9 _ . - in file names.
      const safe = new File([file], file.name.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 100));
      const uploaded = await uploadFirmware(version, safe);
      setMessage({ ok: true, text: `Uploaded ${uploaded.version}` });
      setVersion("");
      setReload((n) => n + 1);
    } catch (err) {
      if (err instanceof AuthError) return onAuthError(err);
      setMessage({ ok: false, text: err instanceof ApiError ? err.message : "Unexpected error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="fw-heading" data-testid="firmware-library">
      <h2 id="fw-heading">Firmware</h2>
      {canUpload && (
        <form className="edit" onSubmit={submit} data-testid="fw-upload">
          <label>
            Version
            <input data-testid="fw-version" required pattern="\d{1,4}\.\d{1,4}\.\d{1,4}" placeholder="1.1.0"
                   value={version} onChange={(e) => setVersion(e.target.value)} />
          </label>
          <label>
            Image
            <input data-testid="fw-file" type="file" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" disabled={busy} data-testid="fw-upload-submit">Upload</button>
        </form>
      )}
      {message && (
        <p role="status" className={message.ok ? "meta" : "low"} data-testid="fw-upload-message">{message.text}</p>
      )}
      {images && images.length === 0 && <p className="meta" data-testid="fw-library-empty">No firmware uploaded yet.</p>}
      {images && images.length > 0 && (
        <ul className="plain" data-testid="fw-library">
          {images.map((f) => (
            <li key={f.id} data-testid={`fw-image-${f.version}`}>
              <span className="mono">{f.version}</span> {f.filename}{" "}
              <span className="meta">
                {f.size} bytes · sha256 {f.checksum.slice(0, 12)}… · {f.uploaded_by}, {formatRelative(f.created_at, now)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
