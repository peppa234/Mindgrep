import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Styleguide · MemoryOS",
  description: "Every token, component state and effect of the MemoryOS design system.",
  robots: { index: false, follow: false },
};

export default function StyleguideLayout({ children }: { children: React.ReactNode }) {
  return children;
}
