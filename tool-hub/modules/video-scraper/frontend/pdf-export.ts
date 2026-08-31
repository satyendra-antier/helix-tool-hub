/** Minimal multi-page text PDF builder (Helvetica / WinAnsi). No external deps. */

type PdfLine = { text: string; size: number };

function sanitizeForPdf(text: string): string {
  return text
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/\u2026/g, "...")
    .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "?");
}

function escapePdfString(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function wrapLines(text: string, maxChars: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split(/\r?\n/)) {
    if (!paragraph.trim()) {
      lines.push("");
      continue;
    }
    let remaining = paragraph;
    while (remaining.length > maxChars) {
      let breakAt = remaining.lastIndexOf(" ", maxChars);
      if (breakAt <= 0) breakAt = maxChars;
      lines.push(remaining.slice(0, breakAt));
      remaining = remaining.slice(breakAt).trimStart();
    }
    if (remaining) lines.push(remaining);
  }
  return lines;
}

function pageContentStream(lines: PdfLine[], pageHeight: number, margin: number): string {
  const parts: string[] = ["BT"];
  let first = true;
  for (const line of lines) {
    const lead = line.size + 4;
    if (first) {
      parts.push(`/F1 ${line.size} Tf`);
      parts.push(`1 0 0 1 ${margin} ${pageHeight - margin} Tm`);
      parts.push(`(${escapePdfString(line.text)}) Tj`);
      first = false;
    } else {
      parts.push(`/F1 ${line.size} Tf`);
      parts.push(`0 -${lead} Td`);
      parts.push(`(${escapePdfString(line.text)}) Tj`);
    }
  }
  parts.push("ET");
  return parts.join("\n");
}

export type PdfExportInput = {
  title: string;
  channel?: string;
  durationSeconds?: number;
  oneLineSummary?: string;
  keyPoints?: string[];
  chapters?: { timestamp_hint: string; title: string }[];
  topics?: string[];
  transcript?: string;
  sourceUrl?: string;
};

export function buildScrapePdf(input: PdfExportInput): Blob {
  const pageWidth = 612;
  const pageHeight = 792;
  const margin = 50;
  const bodySize = 10;
  const titleSize = 16;
  const headingSize = 12;
  const maxChars = 88;
  const usableHeight = pageHeight - margin * 2;

  const content: PdfLine[] = [];
  const push = (text: string, size: number) => content.push({ text: sanitizeForPdf(text), size });
  const pushWrapped = (text: string, size: number) => {
    for (const line of wrapLines(sanitizeForPdf(text), maxChars)) {
      content.push({ text: line, size });
    }
  };

  push(input.title || "Video Scrape", titleSize);
  const metaBits = [
    input.channel,
    input.durationSeconds != null
      ? `${Math.floor(input.durationSeconds / 60)}m ${input.durationSeconds % 60}s`
      : null,
  ].filter(Boolean);
  if (metaBits.length) push(metaBits.join(" · "), 9);
  if (input.sourceUrl) pushWrapped(input.sourceUrl, 8);
  push("", bodySize);

  if (input.oneLineSummary) {
    push("Summary", headingSize);
    pushWrapped(input.oneLineSummary, bodySize);
    push("", bodySize);
  }

  if (input.topics?.length) {
    push("Topics", headingSize);
    pushWrapped(input.topics.join(", "), bodySize);
    push("", bodySize);
  }

  if (input.keyPoints?.length) {
    push("Key Points", headingSize);
    for (const point of input.keyPoints) {
      pushWrapped(`- ${point}`, bodySize);
    }
    push("", bodySize);
  }

  if (input.chapters?.length) {
    push("Chapters", headingSize);
    for (const ch of input.chapters) {
      pushWrapped(`${ch.timestamp_hint}  ${ch.title}`, bodySize);
    }
    push("", bodySize);
  }

  if (input.transcript) {
    push("Transcript", headingSize);
    pushWrapped(input.transcript, bodySize);
  }

  const pages: PdfLine[][] = [];
  let current: PdfLine[] = [];
  let used = 0;
  for (const line of content) {
    const h = line.size + 4;
    if (used + h > usableHeight && current.length > 0) {
      pages.push(current);
      current = [];
      used = 0;
    }
    current.push(line);
    used += h;
  }
  if (current.length) pages.push(current);
  if (!pages.length) pages.push([{ text: "(empty)", size: bodySize }]);

  const objects: (string | null)[] = [null];
  const addObj = (body: string) => {
    objects.push(body);
    return objects.length - 1;
  };

  const fontId = addObj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  const contentIds: number[] = [];
  const pageIds: number[] = [];

  for (const pageLines of pages) {
    const stream = pageContentStream(pageLines, pageHeight, margin);
    const contentId = addObj(
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`
    );
    contentIds.push(contentId);
  }

  const pagesId = objects.length;
  objects.push(null);

  for (let i = 0; i < pages.length; i++) {
    const pageId = addObj(
      `<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] ` +
        `/Contents ${contentIds[i]} 0 R /Resources << /Font << /F1 ${fontId} 0 R >> >> >>`
    );
    pageIds.push(pageId);
  }

  objects[pagesId] =
    `<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(" ")}] /Count ${pageIds.length} >>`;

  const catalogId = addObj(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`);

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [0];
  for (let i = 1; i < objects.length; i++) {
    offsets[i] = pdf.length;
    pdf += `${i} 0 obj\n${objects[i]}\nendobj\n`;
  }
  const xrefPos = pdf.length;
  pdf += `xref\n0 ${objects.length}\n`;
  pdf += "0000000000 65535 f \n";
  for (let i = 1; i < objects.length; i++) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length} /Root ${catalogId} 0 R >>\n`;
  pdf += `startxref\n${xrefPos}\n%%EOF`;

  return new Blob([pdf], { type: "application/pdf" });
}
