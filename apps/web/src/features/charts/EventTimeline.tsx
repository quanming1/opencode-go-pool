import type { EventItem } from "../../types/pool";
import { buildSummary, labelOf } from "./eventSummary";

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

/** 统一事件时间线（C4）：最近事件列表，按 type 渲染徽章与摘要。 */
export function EventTimeline({ events }: { events: EventItem[] }) {
  return (
    <div className="event-timeline" data-testid="event-timeline">
      {events.length === 0 ? (
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
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}