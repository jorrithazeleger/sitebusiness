-- Schoonschip.app: wordt bij installatie gebouwd met osacompile.
-- __PYTHON__ en __SERVER__ worden dan vervangen door de echte paden.
-- Deze app start alleen het Schoonschip-programma (of haalt het naar voren) en stopt dan zelf.

property pythonPath : "__PYTHON__"
property serverPath : "__SERVER__"

on run
	try
		do shell script quoted form of pythonPath & " " & quoted form of serverPath & " --open"
	on error errMsg
		display dialog "Schoonschip kon niet starten:" & return & return & errMsg buttons {"OK"} default button "OK" with icon caution with title "Schoonschip"
	end try
end run
