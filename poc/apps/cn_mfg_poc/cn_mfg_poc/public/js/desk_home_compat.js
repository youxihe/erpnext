/* v16 兼容:旧路由 /desk/home、/app/home 对非管理员会因 getpage('home') 报
 * 「页面 home 未找到」(v16 已无 home Page,仅 Workspace "home")。
 * 在 desk SPA 解析路由之前,把这两个遗留路由整页重定向到标准首页 /desk。
 * 用 sessionStorage 标记防环;管理员同样跳 /desk(等价其原 /desk/setup/home)。*/
(function () {
  try {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    if (path === "/desk/home" || path === "/app/home") {
      if (!sessionStorage.getItem("cn_desk_home_redirected")) {
        sessionStorage.setItem("cn_desk_home_redirected", "1");
        window.location.replace("/desk");
      } else {
        sessionStorage.removeItem("cn_desk_home_redirected");
      }
    } else {
      sessionStorage.removeItem("cn_desk_home_redirected");
    }
  } catch (e) { /* 存储不可用时静默跳过 */ }
})();
