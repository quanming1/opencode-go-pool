import type { SwitchEvent } from "../../types/pool";

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

/** 轮换事件时间线（C2 FR6）：最近切换/状态事件列表。 */
export function SwitchTimeline({ events }: { events: SwitchEvent[] }) {
  return (
    <div className="switch-timeline" data-testid="switch-timeline">
      {events.length === 0 ? (
        <p className="dashboard-empty">暂无轮换事件</p>
      ) : (
        <ul className="switch-timeline__list">
          {events.map((e, idx) => (
            <li className="switch-timeline__item" key={`${e.ts}-${idx}`}>
              <span className="switch-timeline__time">{formatTs(e.ts)}</span>
              <span className="switch-timeline__account">{e.account_id}</span>
              <span className={`switch-kind switch-kind--${e.kind}`}>{e.kind_label}</span>
              {e.reason && <span className="switch-timeline__reason">{e.reason}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
