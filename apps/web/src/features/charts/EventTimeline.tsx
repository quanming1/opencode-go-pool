import { useCallback, useEffect, useState } from "react";
import { fetchEventsPage } from "../../services/api";
import type { EventItem } from "../../types/pool";
import { buildSummary, labelOf } from "./eventSummary";

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

const PAGE_SIZE = 20;
const AUTO_REFRESH_MS = 10_000;

/** 把事件 data/meta 的字段展开成可读行（D1 FR6 丰富字段）。

 * meta 与 data 可能同名字段（如 request_id）——同名只保留一处，避免 React key 冲突。
 */
function detailRows(event: EventItem): Array<[string, string]> {
  const rows: Array<[string, string]> = [];
  const seen = new Set<string>();
  const data = event.data ?? {};
  const meta = event.meta ?? {};
  const push = (k: string, v: unknown): void => {
    if (v === undefined || v === null || seen.has(k)) return;
    seen.add(k);
    rows.push([k, typeof v === "object" ? JSON.stringify(v) : String(v)]);
  };
  push("request_id", meta.request_id);
  push("source", meta.source);
  push("schema_version", meta.schema_version);
  Object.entries(data).forEach(([k, v]) => push(k, v));
  return rows;
}

/** 统一事件时间线（C4 + D1 FR5/FR6）：分页展示 + 丰富字段详情。 */
export function EventTimeline() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (target: number) => {
    setLoading(true);
    try {
      const page = await fetchEventsPage(PAGE_SIZE, target);
      setEvents(page.events);
      setOffset(page.offset);
      setHasMore(page.has_more);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 首帧主动拉取第一页（KeysPanel 同模式）
    void load(0);
  }, [load]);

  // 仅在第一页时自动刷新（保持「最新」）；翻到旧页暂停以免打断浏览。
  useEffect(() => {
    if (offset !== 0) return;
    const timer = window.setInterval(() => void load(0), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [offset, load]);

  const onPrev = (): void => void load(Math.max(0, offset - PAGE_SIZE));
  const onNext = (): void => void load(offset + PAGE_SIZE);

  return (
    <div className="event-timeline" data-testid="event-timeline">
      {error && <p className="dashboard-error">加载事件失败: {error}</p>}
      {events.length === 0 && !loading ? (
        <p className="dashboard-empty">暂无事件</p>
      ) : (
        <ul className="event-timeline__list">
          {events.map((e, idx) => (
            <li className="event-timeline__item" key={`${e.time}-${idx}`}>
              <span className="event-timeline__time">{formatTs(e.time)}</span>
              <span className={`event-type event-type--${e.type}`}>
                {labelOf(e.type)}
              </span>
              <span className="event-timeline__summary">
                {buildSummary(e.type, e.data)}
              </span>
              <details className="event-timeline__detail">
                <summary>字段详情</summary>
                <dl className="event-timeline__fields">
                  {detailRows(e).map(([k, v]) => (
                    <div className="event-timeline__field" key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            </li>
          ))}
        </ul>
      )}
      <div className="event-timeline__pager">
        <button
          type="button"
          className="btn"
          data-testid="events-prev"
          onClick={onPrev}
          disabled={offset <= 0 || loading}
        >
          上一页
        </button>
        <span className="event-timeline__page" data-testid="events-offset">
          第 {Math.floor(offset / PAGE_SIZE) + 1} 页（共 {offset} 条已浏览）
        </span>
        <button
          type="button"
          className="btn"
          data-testid="events-next"
          onClick={onNext}
          disabled={!hasMore || loading}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
