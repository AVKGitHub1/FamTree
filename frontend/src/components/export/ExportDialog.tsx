import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import * as api from "../../api/endpoints";
import type { ExportFormat, ExportPreview, ExportRequest, ExportScope, Orientation } from "../../api/types";
import { BIRTH_DATE } from "../../lib/attributes";
import type { TreeIndex } from "../../lib/treeIndex";
import { useToast } from "../../state/toasts";
import { Dialog } from "../ui/Dialog";

/** What the tree shows now: the generations around the person in focus,
 * narrowed to the people of View Only Selected. */
export interface ExportView {
  window: ExportRequest["window"];
  /** The window leaves out some generations. */
  generationsHidden: boolean;
  people: string[] | null;
}

interface Props {
  index: TreeIndex;
  /** null when nobody is in focus and everyone is shown. */
  view: ExportView | null;
  onClose: () => void;
}

function describeView(view: ExportView | null): string {
  if (!view?.people) return "generations shown now";
  return view.generationsHidden ? "the selected people, in the generations shown" : "only the selected people";
}

const PNG_WIDTHS = [1600, 3200, 6400, 9600, 12800];
const PAGE_SIZES: [string, string][] = [
  ["a4", "A4"],
  ["a3", "A3"],
  ["a2", "A2"],
  ["a1", "A1"],
  ["a0", "A0"],
  ["letter", "US Letter"],
  ["legal", "US Legal"],
  ["tabloid", "Tabloid (11 × 17 in)"],
];

export function ExportDialog({ index, view, onClose }: Props) {
  const notify = useToast();
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [scope, setScope] = useState<ExportScope>(view && (view.people || view.generationsHidden) ? "view" : "full");
  const [attributes, setAttributes] = useState<string[]>(index.definitions.has(BIRTH_DATE) ? [BIRTH_DATE] : []);
  const [parentLinks, setParentLinks] = useState(true);
  const [spouseLinks, setSpouseLinks] = useState(true);
  const [legend, setLegend] = useState(true);
  const [pngWidth, setPngWidth] = useState(3200);
  const [pageSize, setPageSize] = useState("a3");
  const [orientation, setOrientation] = useState<Orientation>("auto");
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const body = useMemo<ExportRequest>(
    () => ({
      format,
      scope,
      window: scope === "view" && view ? view.window : null,
      people: scope === "view" && view ? view.people : null,
      attributes,
      include_parent_links: parentLinks,
      include_spouse_links: spouseLinks,
      include_legend: legend,
      png_width: pngWidth,
      page_size: pageSize,
      orientation,
    }),
    [format, scope, view, attributes, parentLinks, spouseLinks, legend, pngWidth, pageSize, orientation],
  );

  const needsCategory = index.people.size > 1 && !parentLinks && !spouseLinks;
  const shownError = needsCategory ? "Choose at least one kind of relationship to draw." : error;

  useEffect(() => {
    if (needsCategory) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api.previewExport(body).then(
        (result) => {
          if (cancelled) return;
          setPreview(result);
          setError(null);
        },
        (err) => !cancelled && setError(err instanceof ApiError ? err.message : "Preview failed."),
      );
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [body, needsCategory]);

  const download = async () => {
    setDownloading(true);
    try {
      const { blob, filename } = await api.downloadExport(body);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify(`Downloaded ${filename}.`, "success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed.");
    } finally {
      setDownloading(false);
    }
  };

  const toggleAttribute = (id: string) =>
    setAttributes((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));

  return (
    <Dialog
      title="Export"
      size="wide"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={download}
            disabled={downloading || Boolean(shownError)}
          >
            {downloading ? "Preparing…" : `Download ${format.toUpperCase()}`}
          </button>
        </>
      }
    >
      <div className="export">
        <div className="export__options">
          <fieldset className="choice">
            <legend>Format</legend>
            <label>
              <input type="radio" checked={format === "pdf"} onChange={() => setFormat("pdf")} /> PDF
            </label>
            <label>
              <input type="radio" checked={format === "png"} onChange={() => setFormat("png")} /> Image (PNG)
            </label>
          </fieldset>

          <fieldset className="choice">
            <legend>What to include</legend>
            <label>
              <input type="radio" checked={scope === "view"} disabled={!view} onChange={() => setScope("view")} /> Current
              view ({describeView(view)})
            </label>
            <label>
              <input type="radio" checked={scope === "full"} onChange={() => setScope("full")} /> Full tree
            </label>
          </fieldset>

          <fieldset className="checks">
            <legend>Details on each card</legend>
            <p className="hint">Names are always included. Only details you are allowed to see are exported.</p>
            {[...index.definitions.values()].map((d) => (
              <label key={d.id}>
                <input type="checkbox" checked={attributes.includes(d.id)} onChange={() => toggleAttribute(d.id)} /> {d.label}
              </label>
            ))}
          </fieldset>

          <fieldset className="checks">
            <legend>Relationships to draw</legend>
            <label>
              <input type="checkbox" checked={parentLinks} onChange={(e) => setParentLinks(e.target.checked)} /> Parent and
              child
            </label>
            <label>
              <input type="checkbox" checked={spouseLinks} onChange={(e) => setSpouseLinks(e.target.checked)} /> Spouses
            </label>
            <label>
              <input type="checkbox" checked={legend} onChange={(e) => setLegend(e.target.checked)} /> Include a legend
            </label>
          </fieldset>

          {format === "png" ? (
            <div className="field">
              <label htmlFor="export-width">Image width</label>
              <select id="export-width" value={pngWidth} onChange={(e) => setPngWidth(Number(e.target.value))}>
                {PNG_WIDTHS.map((w) => (
                  <option key={w} value={w}>
                    {w.toLocaleString()} px
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="field-row">
              <div className="field">
                <label htmlFor="export-page">Page size</label>
                <select id="export-page" value={pageSize} onChange={(e) => setPageSize(e.target.value)}>
                  {PAGE_SIZES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="export-orientation">Orientation</label>
                <select
                  id="export-orientation"
                  value={orientation}
                  onChange={(e) => setOrientation(e.target.value as Orientation)}
                >
                  <option value="auto">Best fit</option>
                  <option value="portrait">Portrait</option>
                  <option value="landscape">Landscape</option>
                </select>
              </div>
            </div>
          )}
        </div>

        <div className="export__preview" aria-live="polite">
          {preview && !shownError ? (
            <>
              <img src={preview.image} alt={`Preview of the ${format.toUpperCase()} export`} />
              <p className="muted">
                {preview.people} {preview.people === 1 ? "person" : "people"} ·{" "}
                {Math.round(preview.output.width)} × {Math.round(preview.output.height)} {preview.output.unit} · smallest
                text ≈ {preview.text_size.value} {preview.text_size.unit}
              </p>
              {preview.warnings.map((w) => (
                <p key={w} className="warning">
                  ⚠ {w}
                </p>
              ))}
            </>
          ) : shownError ? (
            <p className="error-banner" role="alert">
              {shownError}
            </p>
          ) : (
            <p className="muted">Preparing preview…</p>
          )}
        </div>
      </div>
    </Dialog>
  );
}
