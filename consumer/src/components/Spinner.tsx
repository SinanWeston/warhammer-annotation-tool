export default function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const px = size === 'sm' ? 'w-5 h-5' : size === 'md' ? 'w-8 h-8' : 'w-12 h-12'
  return (
    <div className={`${px} border-2 border-gothic-medium border-t-brass-light rounded-full animate-spin`} />
  )
}
