import {
  Wheat, Flower2, Bean, Sprout, Carrot, Cloud, SquareDashed, Ellipsis, Hourglass, Layers, BrickWall, Snowflake,
  Waves, Droplets, Droplet, DropletOff, CloudRain, GlassWater, Tractor, HandCoins, X, Check, Wallet, Calendar,
  MapPin, Ruler, FileText, Shovel, Bug, Eye, Scissors, Store, CloudSun, Merge, Package, Leaf,
} from "lucide-react";

const MAP = {
  wheat: Wheat, barley: Wheat, raya: Flower2, gram: Bean, potato: Carrot, paddy: Sprout, basmati: Sprout,
  cotton: Cloud, maize: Leaf, fallow: SquareDashed, other: Ellipsis,
  sandy: Hourglass, loam: Layers, clay: BrickWall, salt: Snowflake,
  waves: Waves, tubewell: Droplets, both: Merge, "cloud-rain": CloudRain, sweet: GlassWater, "glass-water": GlassWater,
  droplet: Droplet, droplets: Droplets, tractor: Tractor, rent: HandCoins, x: X, check: Check, wallet: Wallet,
  calendar: Calendar, "map-pin": MapPin, ruler: Ruler, "file-text": FileText, layers: Layers, sprout: Sprout,
  seed: Package, sow: Sprout, fert: Leaf, water: Droplets, weeds: Shovel, watch: Bug, harvest: Scissors,
  sell: Store, weather: CloudSun, eye: Eye,
};

const COUNT = { none: 0, one: 1, few: 2, many: 3 };

export default function Icon({ name, size = 24, className = "", strokeWidth = 1.9 }) {
  if (name in COUNT) {   // irrigation buckets: show how many waterings at a glance
    const n = COUNT[name];
    if (n === 0) return <DropletOff size={size} className={className} strokeWidth={strokeWidth} aria-hidden />;
    return (
      <span className={`inline-flex -space-x-1.5 ${className}`} aria-hidden>
        {Array.from({ length: n }, (_, i) => <Droplet key={i} size={size * 0.82} strokeWidth={strokeWidth} />)}
      </span>
    );
  }
  const C = MAP[name] || Leaf;
  return <C size={size} className={className} strokeWidth={strokeWidth} aria-hidden />;
}

export const CROP_TONE = {
  orange: { text: "text-orange-ink", bg: "bg-orange-soft", solid: "bg-orange", hex: "#D5803B" },
  yellow: { text: "text-yellow-ink", bg: "bg-yellow-soft", solid: "bg-yellow", hex: "#CB9B1E" },
  green: { text: "text-green-ink", bg: "bg-green-soft", solid: "bg-green", hex: "#46A171" },
  blue: { text: "text-blue-ink", bg: "bg-blue-soft", solid: "bg-blue", hex: "#2783DE" },
};
