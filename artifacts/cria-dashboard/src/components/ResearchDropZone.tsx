import { useCallback, useRef, useState } from "react";

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "rst", "text", "csv", "json", "yaml", "yml",
  "tex", "rtf", "org", "adoc", "asciidoc",
]);

const MAX_CHARS = 6000;

async function extractText(file: File): Promise<string> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";

  if (TEXT_EXTENSIONS.has(ext) || file.type.startsWith("text/")) {
    const raw = await file.text();
    return raw.slice(0, MAX_CHARS);
  }

  if (ext === "pdf" || file.type === "application/pdf") {
    try {
      const pdfjsLib = await import("pdfjs-dist");
      // Use a CDN worker URL that is reliable across all environments
      if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;
      }
      const arrayBuffer = await file.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
      const parts: string[] = [];
      let total = 0;
      for (let p = 1; p <= pdf.numPages && total < MAX_CHARS; p++) {
        const page = await pdf.getPage(p);
        const content = await page.getTextContent();
        const pageText = content.items
          .map((item) => ("str" in item ? item.str : ""))
          .join(" ");
        parts.push(pageText);
        total += pageText.length;
      }
      const extracted = parts.join("\n\n").slice(0, MAX_CHARS).trim();
      if (!extracted) throw new Error("no-text");
      return extracted;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg === "no-text") throw new Error("This PDF appears to be image-based (scanned). Copy and paste the text instead.");
      throw new Error("Could not extract text from this PDF. Try copying and pasting the text instead.");
    }
  }

  if (ext === "docx") {
    throw new Error(
      ".docx files are not yet supported. Open the document and paste the text directly, or save it as .txt first.",
    );
  }

  throw new Error(
    `Unsupported file type: .${ext || file.type}. Supported formats: .txt, .md, .pdf, and other plain-text files.`,
  );
}

interface ResearchDropZoneProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  disabled?: boolean;
}

export default function ResearchDropZone({
  value,
  onChange,
  placeholder,
  rows = 3,
  className,
  disabled,
}: ResearchDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [notice, setNotice] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const dragCounter = useRef(0);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showNotice = (type: "ok" | "err", text: string) => {
    setNotice({ type, text });
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 4000);
  };

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) setIsDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setIsDragOver(false);

      const file = e.dataTransfer.files?.[0];
      if (!file) return;

      setExtracting(true);
      try {
        const text = await extractText(file);
        const trimmed = text.trim();
        if (!trimmed) {
          showNotice("err", "File appears to be empty or contains no readable text.");
          return;
        }
        onChange(trimmed);
        const truncated = trimmed.length >= MAX_CHARS;
        showNotice(
          "ok",
          truncated
            ? `Extracted from "${file.name}" (truncated to ${MAX_CHARS.toLocaleString()} chars).`
            : `Extracted from "${file.name}" (${trimmed.length.toLocaleString()} chars).`,
        );
      } catch (err) {
        showNotice("err", err instanceof Error ? err.message : "Could not read file.");
      } finally {
        setExtracting(false);
      }
    },
    [onChange],
  );

  return (
    <div className="relative" onDragEnter={handleDragEnter}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        disabled={disabled || extracting}
        className={className}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      />

      {/* Drag-over overlay */}
      {isDragOver && (
        <div
          className="absolute inset-0 rounded-xl flex flex-col items-center justify-center gap-2 pointer-events-none z-10"
          style={{
            background: "rgba(99,102,241,0.12)",
            border: "2px dashed rgba(99,102,241,0.7)",
            borderRadius: "0.75rem",
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgba(99,102,241,0.9)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          <span className="text-sm font-medium" style={{ color: "rgba(99,102,241,0.95)" }}>
            Drop research brief here
          </span>
          <span className="text-xs" style={{ color: "rgba(99,102,241,0.65)" }}>
            .txt · .md · .pdf · plain text
          </span>
        </div>
      )}

      {/* Extracting spinner */}
      {extracting && (
        <div className="absolute inset-0 rounded-xl flex items-center justify-center gap-2 pointer-events-none z-10 bg-background/60 backdrop-blur-sm">
          <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          <span className="text-sm text-muted-foreground">Extracting text…</span>
        </div>
      )}

      {/* Notice */}
      {notice && (
        <div
          className={`absolute -bottom-8 left-0 right-0 text-xs px-2 py-1 rounded flex items-center gap-1.5 ${
            notice.type === "ok"
              ? "text-emerald-400"
              : "text-red-400"
          }`}
        >
          {notice.type === "ok" ? (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          )}
          {notice.text}
        </div>
      )}
    </div>
  );
}
