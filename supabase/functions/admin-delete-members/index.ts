import "jsr:@supabase/functions-js/edge-runtime.d.ts"
import { createClient } from "npm:@supabase/supabase-js@2"

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { ...corsHeaders, "Content-Type": "application/json" },
})

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders })
  if (request.method !== "POST") return json({ error: "지원하지 않는 요청입니다." }, 405)

  const authorization = request.headers.get("Authorization")
  const token = authorization?.replace(/^Bearer\s+/i, "")
  if (!token) return json({ error: "로그인이 필요합니다." }, 401)

  const supabaseUrl = Deno.env.get("SUPABASE_URL")
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")
  if (!supabaseUrl || !serviceRoleKey) return json({ error: "서버 설정을 확인해 주세요." }, 500)

  const adminClient = createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  })
  const { data: callerData, error: callerError } = await adminClient.auth.getUser(token)
  const caller = callerData.user
  if (callerError || !caller) return json({ error: "관리자 세션이 유효하지 않습니다." }, 401)
  if (caller.app_metadata?.role !== "admin") return json({ error: "관리자만 회원을 삭제할 수 있습니다." }, 403)

  let payload: { ids?: unknown }
  try {
    payload = await request.json()
  } catch {
    return json({ error: "요청 형식이 올바르지 않습니다." }, 400)
  }

  const ids = Array.isArray(payload.ids)
    ? [...new Set(payload.ids.filter((id): id is string => typeof id === "string" && uuidPattern.test(id)))].slice(0, 100)
    : []
  if (!ids.length) return json({ deleted: [], failed: [] })

  const deleted: string[] = []
  const failed: Array<{ id: string; reason: string }> = []

  for (const id of ids) {
    if (id === caller.id) {
      failed.push({ id, reason: "현재 로그인한 관리자 계정은 삭제할 수 없습니다." })
      continue
    }

    const { data: targetData, error: targetError } = await adminClient.auth.admin.getUserById(id)
    if (targetError || !targetData.user) {
      const { error: profileError } = await adminClient.from("profiles").delete().eq("id", id)
      if (profileError) failed.push({ id, reason: "회원 정보를 삭제하지 못했습니다." })
      else deleted.push(id)
      continue
    }
    if (targetData.user.app_metadata?.role === "admin") {
      failed.push({ id, reason: "관리자 계정은 회원 관리에서 삭제할 수 없습니다." })
      continue
    }

    const { error: deleteError } = await adminClient.auth.admin.deleteUser(id)
    if (deleteError) failed.push({ id, reason: "회원 계정을 삭제하지 못했습니다." })
    else deleted.push(id)
  }

  if (deleted.length) {
    await adminClient.from("admin_audit_logs").insert({
      admin_user_id: caller.id,
      action: "delete_members",
      entity_type: "profiles",
      details: { deleted_ids: deleted, requested_count: ids.length, failed_count: failed.length },
    })
  }

  return json({ deleted, failed })
})
