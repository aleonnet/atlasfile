import type { ReactNode } from "react";

type Props = {
  icon: ReactNode;
  title: string;
  description?: string;
};

export function EmptyState({ icon, title, description }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
    </div>
  );
}
