return {
    LrSdkVersion = 11.0,
    LrSdkMinimumVersion = 8.0,

    LrToolkitIdentifier = 'com.superpicky.birdid.lightroom',
    LrPluginName = "慧眼选鸟 Lightroom 插件",

    LrInitPlugin = 'PluginInit.lua',

    -- 导出服务（通过导出菜单调用）
    LrExportServiceProvider = {
        {
            title = "慧眼选鸟 - 鸟类识别",
            file = 'SuperBirdIDExportServiceProvider.lua',
        },
    },

    -- 图库菜单项（通过 图库 → 增效工具 调用）
    LrLibraryMenuItems = {
        {
            title = "慧眼选鸟 - 识别当前照片",
            file = 'LibraryMenuItem.lua',
        },
    },

    VERSION = { major=4, minor=0, revision=0, build=1, },
}
