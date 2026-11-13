        // Loaded last, so everything above exists before anything runs.

        // Destination picker - initialise on page load so it's ready before the first search
        initDestinationPicker();

        // initApp waits on the network, so it starts only once every file has
        // loaded; started earlier, it could call into one still on its way.
        initApp();
