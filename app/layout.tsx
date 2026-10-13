import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "figtoapk — From design to Android", description: "Turn a web-ready design export ZIP into an Android APK build." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
