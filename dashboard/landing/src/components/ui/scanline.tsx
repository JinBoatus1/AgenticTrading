export default function Scanline() {
  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden mix-blend-overlay">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%)] bg-[length:100%_4px] opacity-30"></div>
    </div>
  );
}
