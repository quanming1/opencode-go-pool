/** 左侧 tab 导航（C3 FR7 左右分栏；E2 i18n 文案）。 */
import { useI18n } from "../i18n";

export type TabId = "usage" | "keys";

const TABS: { id: TabId; labelKey: "nav.usage" | "nav.keys" }[] = [
  { id: "usage", labelKey: "nav.usage" },
  { id: "keys", labelKey: "nav.keys" },
];

export function Sidebar({
  active,
  onChange,
}: {
  active: TabId;
  onChange: (tab: TabId) => void;
}) {
  const { t } = useI18n();
  return (
    <nav className="sidebar" data-testid="sidebar">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`sidebar-tab${active === tab.id ? " sidebar-tab--active" : ""}`}
          onClick={() => onChange(tab.id)}
          data-testid={`tab-${tab.id}`}
        >
          {t(tab.labelKey)}
        </button>
      ))}
    </nav>
  );
}
