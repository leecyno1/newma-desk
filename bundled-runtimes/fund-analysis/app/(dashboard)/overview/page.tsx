import { redirect } from 'next/navigation'

export default function ProfessionalResearchOverviewRedirect() {
  // mod workspace 白名单无 overview；重定向到模组入口（与 /mod/fund-research 等价）
  redirect('/mod/fund-research/discover')
}
