import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Deadlock Stats',
  description: 'HLTV equivalent for Valve\'s Deadlock',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  )
}