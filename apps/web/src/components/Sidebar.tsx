/** 左侧 tab 导航（C3 FR7 左右分栏）。 */

export type TabId = "usage" | "keys";

const TABS: { id: TabId; label: string }[] = [
  { id: "usage", label: "用量信息" },
  { id: "keys", label: "API Key 管理" },
];

export function Sidebar({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
}) {
  return (
    <nav className="sidebar" data-testid="sidebar">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`sidebar-tab${active === t.id ? " sidebar-tab--active" : ""}`}
          onClick={() => onChange(t.id)}
          data-testid={`tab-${t.id}`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  );
}
