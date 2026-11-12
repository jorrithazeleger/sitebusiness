-- Rekenblad.app: wordt bij installatie gebouwd met osacompile.
-- __PYTHON__ en __SERVER__ worden dan vervangen door de echte paden.
-- Deze app geeft alleen door: de vensters zelf horen bij het Rekenblad-programma dat hij start.

property pythonPath : "__PYTHON__"
property serverPath : "__SERVER__"

on run
	launchWith({})
end run

-- Bestanden die je opent vanuit de Finder, Mail of het Dock komen hier binnen.
on open theItems
	set paths to {}
	repeat with f in theItems
		set end of paths to POSIX path of f
	end repeat
	launchWith(paths)
end open

on launchWith(paths)
	set cmd to quoted form of pythonPath & " " & quoted form of serverPath & " --open"
	repeat with p in paths
		set cmd to cmd & " " & quoted form of (p as text)
	end repeat
	try
		do shell script cmd
	on error errMsg
		display dialog "Rekenblad kon dit niet openen:" & return & return & errMsg buttons {"OK"} default button "OK" with icon caution with title "Rekenblad"
	end try
end launchWith
