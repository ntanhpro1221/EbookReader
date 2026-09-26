package vn.ebookreader.player

import android.os.Bundle
import com.getcapacitor.BridgeActivity

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(PlayerPlugin::class.java)
        registerPlugin(LibraryPlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
